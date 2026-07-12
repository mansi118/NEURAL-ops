"""Fidelity ingestion — turn a live HUMAN VERDICT into a persisted run-event the clock folds.

This is the write side of the human-verdict signal source (see fidelity-signal-generation): the Decision
Queue emits `m.neop.verdict {proposal_id, verdict}`; the bridge resolves which SEAT's output was judged
and calls `record_verdict`, which builds an authoritative human-verdict run-event (runtime.shadow.
human_verdict_event) and appends it to the palace INTERIM run_events store (memory.put_run_event,
kind="human_verdict"). The shadow-fidelity runner then folds it into `human_only` fidelity.

PURE except the injected `put` (the palace write) — offline-gradeable with a stub. The SEAT is an
explicit input: a verdict is about a NEop's output, and the proposal must carry that originating seat
(producer contract) — this module does not guess it. core.py untouched; no wall-clock here.
"""
from __future__ import annotations

from runtime.shadow import human_verdict_event


def _default_put(tenant, seat, event, *, kind, ts):
    from runtime.memory import put_run_event   # lazy: credential gate + network only on live use
    return put_run_event(tenant, seat, event, kind=kind, ts=ts)


def record_verdict(tenant, seat, verdict, *, proposal_id=None, field="decision_style",
                   kind="structural", decision_class="selective", ts=None, put=None):
    """Persist a Decision-Queue approve/reject as an authoritative human-verdict run-event for `seat`
    (the NEop whose output was judged). `verdict` is 'approve'|'reject' (or a bool). Returns the palace
    put result. `put` is injectable (memory.put_run_event live, a stub in tests)."""
    event = human_verdict_event(verdict, field=field, kind=kind,
                                decision_class=decision_class, proposal_id=proposal_id)
    _put = put or _default_put
    return _put(tenant, seat, event, kind="human_verdict", ts=ts)
