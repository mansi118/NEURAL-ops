"""T4 tests for AuditTap — the durable, 100%-coverage palace-op audit (jsonl fallback)."""
import os

import pytest

from neop_jcode_adapter.audit_tap import AuditTap, seat_filename
from neop_jcode_adapter.palace_mcp_shim import PalaceShim

FIXED = lambda: 1_750_000_000.0  # deterministic clock


def tap(tmp_path, **kw):
    return AuditTap(str(tmp_path), clock=FIXED, **kw)


# ── construction / destination guarantee ──────────────────────────────────────
def test_no_destination_raises():
    with pytest.raises(ValueError):
        AuditTap(audit_dir=None)  # no dir, no sink → an audit tap that audits nowhere


def test_sink_only_is_allowed():
    rows = []
    t = AuditTap(audit_dir=None, sink=rows.append, clock=FIXED)
    t.emit({"palaceId": "p", "neopId": "a", "tool": "palace_search"})
    assert rows and rows[0]["tool"] == "palace_search"


# ── enrichment + per-seat routing ─────────────────────────────────────────────
def test_emit_enriches_and_routes_per_seat(tmp_path):
    t = tap(tmp_path)
    rec = t.emit({"palaceId": "pal", "neopId": "aria", "tool": "palace_remember"})
    assert rec["kind"] == "palace_op"
    assert rec["ts"] == 1_750_000_000.0 and rec["ts_iso"].startswith("2025-")
    path = tmp_path / seat_filename("pal", "aria")
    assert path.exists()
    assert list(t.records_for(("pal", "aria")))[0]["tool"] == "palace_remember"


def test_two_seats_isolated_files(tmp_path):
    t = tap(tmp_path)
    t.emit({"palaceId": "pal", "neopId": "aria", "tool": "palace_search"})
    t.emit({"palaceId": "pal", "neopId": "recon", "tool": "palace_search"})
    assert len(list(t.records_for(("pal", "aria")))) == 1
    assert len(list(t.records_for(("pal", "recon")))) == 1


# ── 100% palace-op coverage: shim wired to the tap ────────────────────────────
def test_shim_to_tap_gives_full_coverage(tmp_path):
    t = tap(tmp_path)

    def transport(url, body, headers):
        return 200, {"status": "ok", "data": {}}

    aria = PalaceShim(palace_url="u", palace_id="pal", neop_id="aria", transport=transport, audit=t.emit)
    recon = PalaceShim(palace_url="u", palace_id="pal", neop_id="recon", transport=transport, audit=t.emit)
    for _ in range(3):
        aria.call("palace_search", {"query": "x"})
    recon.call("palace_remember", {"content": "y"})
    # every single call produced exactly one audit row in the right seat file
    assert len(list(t.records_for(("pal", "aria")))) == 3
    assert len(list(t.records_for(("pal", "recon")))) == 1
    # rejected ops never reach the palace, so they aren't palace-ops — but they DO raise (visible),
    # never silently pass: a scope-spoof attempt is refused before any audit row is written.
    from neop_jcode_adapter.palace_mcp_shim import ScopeSpoofRejected
    with pytest.raises(ScopeSpoofRejected):
        aria.call("palace_search", {"query": "x", "neopId": "recon"})
    assert len(list(t.records_for(("pal", "aria")))) == 3  # unchanged


# ── transcript export ─────────────────────────────────────────────────────────
def test_export_transcript_records_reference(tmp_path):
    t = tap(tmp_path)
    rec = t.export_transcript(("pal", "aria"), "s3://transcripts/aria/sess1.json", meta={"turns": 12})
    assert rec["kind"] == "transcript" and rec["transcript_ref"].endswith("sess1.json")
    assert rec["turns"] == 12
    assert any(r["kind"] == "transcript" for r in t.records_for(("pal", "aria")))


# ── fail-loud on unwritable destination ───────────────────────────────────────
def test_write_failure_raises(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")
    t = AuditTap(str(blocker / "under_a_file"), clock=FIXED)  # parent is a file → makedirs fails
    with pytest.raises(OSError):
        t.emit({"palaceId": "p", "neopId": "a", "tool": "palace_search"})


# ── sink forwarding alongside jsonl ───────────────────────────────────────────
def test_sink_and_jsonl_both_receive(tmp_path):
    rows = []
    t = tap(tmp_path, sink=rows.append)
    t.emit({"palaceId": "p", "neopId": "a", "tool": "palace_search"})
    assert len(rows) == 1
    assert len(list(t.records_for(("p", "a")))) == 1
