"""AuditTap — every palace op + the session transcript → durable audit (plan §3.6 / task T4).

Target (post-substrate): NATS subject → ClickHouse (nc-audit, S0.5). Pre-S0 fallback (this build):
append-only per-seat `<audit_dir>/<palaceId>__<neopId>.jsonl`. 100% palace-op audit coverage is a
hard acceptance bar (§5); no silent tool surfaces (§6).

Wiring: pass `AuditTap(...).emit` as the shim's `audit=` callable — its signature matches the event
dict the shim already produces. Doing so SUPERSEDES the shim's built-in zero-config jsonl fallback
(same file layout, so the two are interchangeable). When the substrate lands, pass a `sink` callable
(NATS/ClickHouse shipper); the jsonl stays as the durable local mirror — a config swap, not a rewrite.

Coverage stance: an AuditTap with NO destination (no audit_dir and no sink) raises at construction —
an audit tap that audits nowhere is a silent-surface foot-gun. A write failure raises (loud): an
unauditable environment must not run.
"""
from __future__ import annotations

import os
from typing import Callable, Iterator, Optional, Tuple

from ._jsonl import append_jsonl, default_clock, now_fields, read_jsonl

SeatId = Tuple[str, str]  # (palaceId, neopId)


def seat_filename(palace_id: str, neop_id: str) -> str:
    return f"{palace_id or '_unscoped'}__{neop_id or '_unscoped'}.jsonl"


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
        if not self.audit_dir and self._sink is None:
            raise ValueError(
                "AuditTap has no destination: set audit_dir (or NEOP_AUDIT_DIR) or pass a sink"
            )
        self._clock = clock or default_clock

    # --- core ---
    def emit(self, event: dict) -> dict:
        """Enrich + persist one audit record. Returns the stored record. Matches the shim's
        `audit` callable signature, so `PalaceShim(audit=tap.emit)` gives 100% palace-op coverage."""
        record = dict(event)
        record.setdefault("kind", "palace_op")
        record.update(now_fields(self._clock))
        if self.audit_dir:
            append_jsonl(self._path_for(record), record)
        if self._sink is not None:
            self._sink(record)
        return record

    def export_transcript(self, seat: SeatId, transcript_ref: str, *, meta: Optional[dict] = None) -> dict:
        """Record a session-end transcript export (the reference, not the bytes). The actual capture
        of the jcode transcript is box-gated (supervisor/T3); this is the auditable record of it."""
        palace_id, neop_id = seat
        ev = {"kind": "transcript", "palaceId": palace_id, "neopId": neop_id,
              "transcript_ref": transcript_ref}
        if meta:
            ev.update(meta)
        return self.emit(ev)

    # --- readback (verification / Day-90 measurement) ---
    def records_for(self, seat: SeatId) -> Iterator[dict]:
        if not self.audit_dir:
            return iter(())
        return read_jsonl(os.path.join(self.audit_dir, seat_filename(*seat)))

    def _path_for(self, record: dict) -> str:
        return os.path.join(
            self.audit_dir, seat_filename(record.get("palaceId", ""), record.get("neopId", ""))
        )
