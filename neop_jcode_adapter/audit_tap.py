"""AuditTap — every palace op (allow AND deny) → durable audit (plan §3.6 / task T4).

Target (post-substrate): NATS subject → ClickHouse (nc-audit, S0.5). Pre-S0 fallback (this build):
append-only per-seat `<audit_dir>/<palaceId>__<neopId>.jsonl`.

WHY THIS MATTERS (per review 2026-06-18): while the ACL is honest-caller / fail-open (until the S0.3
flip), enforcement TRUSTS the asserted identity — so this audit stream is the ONLY instrument that can
prove the Day-90 "zero isolation violations in 30d" bar. That proof only holds if we tap **allows AND
denies both**: a denial-only log can't distinguish "zero leaks" from "leaks we never recorded." Hence
`make_event` requires `result` and every line carries `palaceId`+`neopId`+`denied_at_layer`.

DESIGN CONTRACT (so S0.5 is an ingest swap, not a schema migration):
  * The jsonl line IS the eventual ClickHouse row — a locked field set (`make_event`):
    who (`actor`) · when (`ts`/`ts_iso`) · what (`action`) · on whom (`target`) · with what permission
    (`permission`) · result (`allow`/`deny`) · `denied_at_layer` · always `palaceId`+`neopId`.
  * Metadata ONLY — never raw payloads, message bodies, key material, or arg VALUES (this stream is
    headed for 7-year retention). We record `arg_keys` (the KEYS), never the args.
  * Non-fatal: a failed write must NOT fail the operation (the palace op already happened). But a
    SILENT drop during the fail-open window is a hole, so a failed write logs `AUDIT-DROP` to stderr
    and bumps `.dropped` — visible and countable, never silent.
  * Swappable seam: `emit(event)` is the stable interface; the jsonl writer and the optional `sink`
    (NATS/ClickHouse shipper) are interchangeable impls — like `runtime/memory.py` is embedder-agnostic.

Wiring: pass `AuditTap(...).emit` as the shim's `audit=` callable → 100% palace-op coverage.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Callable, Iterator, Optional, Tuple

from ._jsonl import append_jsonl, default_clock, now_fields, read_jsonl

SeatId = Tuple[str, str]  # (palaceId, neopId)

AUDIT_SCHEMA_VERSION = 1
RESULT_ALLOW = "allow"
RESULT_DENY = "deny"

# denial layers (mirrors the broker Gate C / Gate E classification)
LAYER_ADAPTER_SHIM = "adapter_shim"   # the shim refused before the call (allowlist / scope-spoof)
LAYER_CONVEX_SOT = "convex_sot"       # the palace returned 403
LAYER_PALACE_ERROR = "palace_error"   # non-403 error from the palace


def seat_filename(palace_id: str, neop_id: str) -> str:
    return f"{palace_id or '_unscoped'}__{neop_id or '_unscoped'}.jsonl"


def make_event(
    *,
    palace_id: str,
    neop_id: str,
    action: str,
    result: str,
    actor: Optional[str] = None,
    target: Optional[dict] = None,
    permission: Optional[dict] = None,
    denied_at_layer: Optional[str] = None,
    reason: Optional[str] = None,
    http_status: Optional[int] = None,
    result_status: Optional[str] = None,
    arg_keys: Optional[list] = None,
    kind: str = "palace_op",
) -> dict:
    """Build a canonical audit record (the ClickHouse row, minus the ts which emit() stamps).

    arg_keys MUST be keys only (no values) — the metadata-only invariant. A denial MUST name the layer
    it was denied at, so the audit stream can attribute every refusal."""
    if result not in (RESULT_ALLOW, RESULT_DENY):
        raise ValueError(f"result must be allow|deny, got {result!r}")
    if result == RESULT_DENY and not denied_at_layer:
        raise ValueError("a denial must record denied_at_layer (allow/deny both, attributable)")
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "kind": kind,
        "palaceId": palace_id,                 # tenant — every line
        "neopId": neop_id,                     # seat — every line
        "actor": actor or neop_id,             # who
        "action": action,                      # what
        "target": target if target is not None else {"palaceId": palace_id, "neopId": neop_id},  # on whom
        "permission": permission or {"scope": "env-baked", "signed": False},  # with what permission
        "result": result,                      # result
        "denied_at_layer": denied_at_layer,    # where denied (None for allow)
        "reason": reason,
        "http_status": http_status,
        "result_status": result_status,
        "arg_keys": list(arg_keys) if arg_keys is not None else [],  # KEYS only — never values
    }


class AuditTap:
    def __init__(
        self,
        audit_dir: Optional[str] = None,
        *,
        sink: Optional[Callable[[dict], None]] = None,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.audit_dir = audit_dir if audit_dir is not None else os.environ.get("NEOP_AUDIT_DIR")
        self._sink = sink
        # Fail-fast on MISCONFIG (a tap that audits nowhere) — distinct from per-op write drops, which
        # are fail-soft below.
        if not self.audit_dir and self._sink is None:
            raise ValueError(
                "AuditTap has no destination: set audit_dir (or NEOP_AUDIT_DIR) or pass a sink"
            )
        self._clock = clock or default_clock
        self.dropped = 0

    # --- core ---
    def emit(self, event: dict) -> dict:
        """Enrich + persist one audit record. NEVER raises into the caller (a failed audit write must
        not fail the palace op) — a drop is logged to stderr and counted instead."""
        record = dict(event)
        record.setdefault("kind", "palace_op")
        record.setdefault("schema_version", AUDIT_SCHEMA_VERSION)
        record.update(now_fields(self._clock))
        self._persist(record)
        return record

    def export_transcript(self, seat: SeatId, transcript_ref: str, *, meta: Optional[dict] = None) -> dict:
        """Record a session-end transcript export (the reference only — never the bytes). Capture of
        the jcode transcript itself is box-gated (supervisor/T3)."""
        palace_id, neop_id = seat
        ev = make_event(palace_id=palace_id, neop_id=neop_id, action="transcript_export",
                        result=RESULT_ALLOW, kind="transcript")
        ev["transcript_ref"] = transcript_ref
        if meta:
            ev.update(meta)
        return self.emit(ev)

    # --- readback (verification / Day-90 measurement) ---
    def records_for(self, seat: SeatId) -> Iterator[dict]:
        if not self.audit_dir:
            return iter(())
        return read_jsonl(os.path.join(self.audit_dir, seat_filename(*seat)))

    # --- internals ---
    def _persist(self, record: dict) -> None:
        if self.audit_dir:
            try:
                append_jsonl(self._path_for(record), record)
            except Exception as exc:  # fail-soft: never fail the op, but never silently drop
                self._on_drop(record, exc)
        if self._sink is not None:
            try:
                self._sink(record)
            except Exception as exc:
                self._on_drop(record, exc)

    def _on_drop(self, record: dict, exc: Exception) -> None:
        self.dropped += 1
        marker = {k: record.get(k) for k in ("palaceId", "neopId", "action", "result", "denied_at_layer")}
        sys.stderr.write(f"AUDIT-DROP {json.dumps(marker)} err={type(exc).__name__}: {exc}\n")
        sys.stderr.flush()

    def _path_for(self, record: dict) -> str:
        return os.path.join(
            self.audit_dir, seat_filename(record.get("palaceId", ""), record.get("neopId", ""))
        )
