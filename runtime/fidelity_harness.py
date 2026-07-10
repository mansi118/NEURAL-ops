"""Fidelity harness (Flow 5→6 assembly) — fold a batch of finished-run shadow events into a seat's
twin via the Curator, in one pure pass.

This is the capstone that composes the leaf modules — `shadow` (grade + event adapter), `judge`
(LLM-as-judge), `curator` (fidelity clock) — behind INJECTED I/O seams (event source, judge, twin
load/save). So the whole loop is offline-gradeable here, and the LIVE harness only swaps the seams:
the Convex run-log reader for `load_events`, the in-VPC Nova call for `judge`, and palace
`get_twin`/`put_twin` for `load_twin`/`save_twin`. No wall-clock, no I/O in this module; core.py
untouched. The nightly cadence that calls `FidelityLoop.tick` is a scheduling concern (EventBridge),
not logic — same posture as every other backend seam in the runtime.
"""
from __future__ import annotations

from runtime.shadow import signals_from_events, recent, fidelity_breakdown
from runtime.curator import curate


def run_fidelity_pass(events, twin, *, judge=None, edits=None, window=None,
                      sustained_days=0, overrides=0, retune_accepted=False,
                      field="decision_style", kind="structural"):
    """One pure pass: grade `events` → (optional) trailing window → `curate` the twin. Returns the
    curator result plus a `breakdown` (blended/human-only/machine-only) and the scored count."""
    signals = signals_from_events(events, judge=judge, field=field, kind=kind)
    if window:
        signals = recent(signals, window)
    result = curate(twin, signals, edits or [], sustained_days=sustained_days,
                    overrides=overrides, retune_accepted=retune_accepted)
    result["breakdown"] = fidelity_breakdown(signals)
    result["scored"] = result["breakdown"]["n_scored"]
    return result


def _stored_fidelity(twin):
    return ((twin or {}).get("signals") or {}).get("agreement_rate_30d")


def should_persist(old_twin, result):
    """Persist when the curator bumped the version (a committed edit or a maturity transition) OR the
    fidelity score moved — the latter has no version bump but is worth recording for observability. A
    no-op pass (no events, nothing changed) writes nothing."""
    if result.get("transitioned") or result.get("committed"):
        return True
    return result.get("fidelity") != _stored_fidelity(old_twin)


class FidelityLoop:
    """Stateful driver over injected seams. `load_twin(tenant, seat) -> twin|None`,
    `save_twin(tenant, seat, twin)`, `load_events(tenant, seat) -> [event]`, and `judge` are all
    supplied by the caller — in-memory offline, Convex/Nova live."""

    SEED = {"maturity": "seed", "version": 0}

    def __init__(self, load_twin, save_twin, load_events, *, judge=None):
        self.load_twin = load_twin
        self.save_twin = save_twin
        self.load_events = load_events
        self.judge = judge

    def tick(self, tenant, seat, *, sustained_days=0, window=None, edits=None):
        twin = self.load_twin(tenant, seat) or dict(self.SEED)
        events = self.load_events(tenant, seat) or []
        result = run_fidelity_pass(events, twin, judge=self.judge, edits=edits, window=window,
                                   sustained_days=sustained_days)
        persisted = should_persist(twin, result)
        if persisted:
            self.save_twin(tenant, seat, result["twin"])
        result["persisted"] = persisted
        return result
