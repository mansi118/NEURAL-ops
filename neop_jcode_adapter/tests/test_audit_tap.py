"""T4 tests for AuditTap — canonical-row audit, allow+deny coverage, non-fatal, metadata-only."""
import json

import pytest

from neop_jcode_adapter.audit_tap import (
    AuditTap,
    LAYER_ADAPTER_SHIM,
    LAYER_CONVEX_SOT,
    make_event,
    seat_filename,
)
from neop_jcode_adapter.palace_mcp_shim import PalaceShim, ScopeSpoofRejected

FIXED = lambda: 1_750_000_000.0  # deterministic clock


def tap(tmp_path, **kw):
    return AuditTap(str(tmp_path), clock=FIXED, **kw)


# ── canonical record (the eventual ClickHouse row) ────────────────────────────
def test_make_event_has_locked_field_set():
    ev = make_event(palace_id="pal", neop_id="aria", action="palace_search", result="allow")
    for k in ("schema_version", "palaceId", "neopId", "actor", "action", "target",
              "permission", "result", "denied_at_layer", "arg_keys"):
        assert k in ev
    assert ev["actor"] == "aria" and ev["target"] == {"palaceId": "pal", "neopId": "aria"}


def test_make_event_deny_requires_layer():
    with pytest.raises(ValueError):
        make_event(palace_id="p", neop_id="a", action="x", result="deny")  # no denied_at_layer
    ok = make_event(palace_id="p", neop_id="a", action="x", result="deny",
                    denied_at_layer=LAYER_ADAPTER_SHIM)
    assert ok["denied_at_layer"] == "adapter_shim"


def test_emit_stamps_time_and_persists(tmp_path):
    t = tap(tmp_path)
    rec = t.emit(make_event(palace_id="pal", neop_id="aria", action="palace_remember", result="allow"))
    assert rec["ts"] == 1_750_000_000.0 and rec["ts_iso"].startswith("2025-")
    assert list(t.records_for(("pal", "aria")))[0]["action"] == "palace_remember"


# ── construction / destination guarantee ──────────────────────────────────────
def test_no_destination_raises():
    with pytest.raises(ValueError):
        AuditTap(audit_dir=None)


def test_sink_only_allowed():
    rows = []
    AuditTap(audit_dir=None, sink=rows.append, clock=FIXED).emit(
        make_event(palace_id="p", neop_id="a", action="palace_search", result="allow"))
    assert rows[0]["action"] == "palace_search"


# ── per-seat routing ──────────────────────────────────────────────────────────
def test_two_seats_isolated_files(tmp_path):
    t = tap(tmp_path)
    t.emit(make_event(palace_id="pal", neop_id="aria", action="palace_search", result="allow"))
    t.emit(make_event(palace_id="pal", neop_id="recon", action="palace_search", result="allow"))
    assert len(list(t.records_for(("pal", "aria")))) == 1
    assert len(list(t.records_for(("pal", "recon")))) == 1
    assert (tmp_path / seat_filename("pal", "aria")).exists()


# ── 100% coverage incl. denials: shim wired to the tap ────────────────────────
def test_shim_to_tap_taps_allows_and_denies(tmp_path):
    t = tap(tmp_path)

    def ok_transport(url, body, headers):
        return 200, {"status": "ok", "data": {}}

    aria = PalaceShim(palace_url="u", palace_id="pal", neop_id="aria", transport=ok_transport, audit=t.emit)
    for _ in range(3):
        aria.call("palace_search", {"query": "x"})
    # a cross-seat spoof attempt: raises AND lands a deny row (not silently dropped)
    with pytest.raises(ScopeSpoofRejected):
        aria.call("palace_search", {"query": "x", "neopId": "recon"})
    rows = list(t.records_for(("pal", "aria")))
    assert [r["result"] for r in rows] == ["allow", "allow", "allow", "deny"]
    deny = rows[-1]
    assert deny["denied_at_layer"] == LAYER_ADAPTER_SHIM and deny["reason"] == "scope_spoof"


def test_palace_403_tapped_as_convex_sot_deny(tmp_path):
    t = tap(tmp_path)

    def deny_transport(url, body, headers):
        return 403, {"status": "error"}

    s = PalaceShim(palace_url="u", palace_id="pal", neop_id="aria", transport=deny_transport, audit=t.emit)
    s.call("palace_search", {"query": "x"})
    assert list(t.records_for(("pal", "aria")))[0]["denied_at_layer"] == LAYER_CONVEX_SOT


# ── metadata only — no payload/secret reaches the 7-year stream ───────────────
def test_no_arg_values_or_secrets_in_jsonl(tmp_path):
    t = tap(tmp_path)

    def ok_transport(url, body, headers):
        return 200, {"status": "ok", "data": {}}

    s = PalaceShim(palace_url="u", palace_id="pal", neop_id="aria", transport=ok_transport, audit=t.emit)
    s.call("palace_remember", {"content": "SUPER_SECRET_xyz", "wingName": "team"})
    raw = (tmp_path / seat_filename("pal", "aria")).read_text()
    assert "SUPER_SECRET_xyz" not in raw          # the value never lands
    assert '"arg_keys"' in raw and "content" in raw  # only the KEYS are recorded


# ── non-fatal: a failed write must not fail the op, but must not be silent ─────
def test_write_failure_is_nonfatal_and_logged(tmp_path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")
    t = AuditTap(str(blocker / "under_a_file"), clock=FIXED)  # parent is a file → write fails
    rec = t.emit(make_event(palace_id="p", neop_id="a", action="palace_search", result="allow"))
    assert rec["action"] == "palace_search"   # emit returned normally — caller op not failed
    assert t.dropped == 1
    assert "AUDIT-DROP" in capsys.readouterr().err  # loud, not silent


# ── transcript export ─────────────────────────────────────────────────────────
def test_export_transcript_records_reference(tmp_path):
    t = tap(tmp_path)
    rec = t.export_transcript(("pal", "aria"), "s3://transcripts/sess1.json", meta={"turns": 12})
    assert rec["kind"] == "transcript" and rec["transcript_ref"].endswith("sess1.json")
    assert rec["turns"] == 12


def test_sink_and_jsonl_both_receive(tmp_path):
    rows = []
    t = tap(tmp_path, sink=rows.append)
    t.emit(make_event(palace_id="p", neop_id="a", action="palace_search", result="allow"))
    assert len(rows) == 1 and len(list(t.records_for(("p", "a")))) == 1
