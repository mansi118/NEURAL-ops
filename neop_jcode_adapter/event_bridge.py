"""EventBridge — NEop lifecycle + significant events → the dashboard / other NEops (plan §3.6 / T4).

Target (post-substrate): NATS subjects (S0.3+). Pre-S0 fallback (this build): a single append-only
`events.jsonl` log. Lifecycle states: started / stopped / crashed / promoted. Like AuditTap, a `sink`
hook makes the NATS cutover a config swap, not a rewrite.

Audit vs events: AuditTap = the durable, per-seat, 100%-coverage RECORD of palace ops (compliance /
Day-90 measurement). EventBridge = a lighter lifecycle/notification STREAM for observers. Distinct
sinks on purpose.
"""
from __future__ import annotations

import os
from typing import Callable, Iterator, Optional, Tuple

from ._jsonl import append_jsonl, default_clock, now_fields, read_jsonl

SeatId = Tuple[str, str]

LIFECYCLE_STATES = frozenset({"started", "stopped", "crashed", "promoted"})


class EventBridge:
    def __init__(
        self,
        log_path: Optional[str] = None,
        *,
        sink: Optional[Callable[[str, dict], None]] = None,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.log_path = log_path if log_path is not None else os.environ.get("NEOP_EVENT_LOG")
        self._sink = sink
        if not self.log_path and self._sink is None:
            raise ValueError(
                "EventBridge has no destination: set log_path (or NEOP_EVENT_LOG) or pass a sink"
            )
        self._clock = clock or default_clock

    def publish(self, subject: str, event: Optional[dict] = None) -> dict:
        record = {"subject": subject}
        if event:
            record.update(event)
        record.update(now_fields(self._clock))
        if self.log_path:
            append_jsonl(self.log_path, record)
        if self._sink is not None:
            self._sink(subject, record)
        return record

    def lifecycle(self, seat: SeatId, state: str, **meta) -> dict:
        """Publish a NEop lifecycle transition. Unknown states raise — the lifecycle vocabulary is
        closed so the dashboard can rely on it (no silent typo'd subjects)."""
        if state not in LIFECYCLE_STATES:
            raise ValueError(f"unknown lifecycle state {state!r}; known: {sorted(LIFECYCLE_STATES)}")
        palace_id, neop_id = seat
        return self.publish(
            f"neop.lifecycle.{state}",
            {"palaceId": palace_id, "neopId": neop_id, "state": state, **meta},
        )

    # convenience
    def started(self, seat: SeatId, **meta) -> dict:
        return self.lifecycle(seat, "started", **meta)

    def stopped(self, seat: SeatId, **meta) -> dict:
        return self.lifecycle(seat, "stopped", **meta)

    def crashed(self, seat: SeatId, **meta) -> dict:
        return self.lifecycle(seat, "crashed", **meta)

    def promoted(self, seat: SeatId, **meta) -> dict:
        return self.lifecycle(seat, "promoted", **meta)

    # readback (verification / dashboard backfill)
    def records(self) -> Iterator[dict]:
        if not self.log_path:
            return iter(())
        return read_jsonl(self.log_path)
