"""Flywheel harness (Flow 8 assembly) — drive the automation flywheel over a corpus of finished runs,
behind injected seams.

`runtime/flywheel.py` is the pure five-gate logic (observe → surface FW1-3 → triage FW4-5). This is the
driver that reads the run-log, observes each run, runs the gates, and routes materialized scaffold SPECS
to the Decision Queue — persisting do-not-re-surface ACROSS passes so a nightly cadence never re-proposes
a shape it already surfaced (flywheel.run_flywheel only threads that within one batch). Live swaps the
seams: the Convex/audit run-log for `load_runs`, the catalog query for `load_existing`, the Decision
Queue for `approvals` + `emit`, and a durable marker store for `surfaced`. Pure given the seams; no
wall-clock, no I/O here. Nothing materializes an agent — the output is a spec a human runs (FW-5).
"""
from __future__ import annotations

from runtime.flywheel import (observe, surface, triage,  # noqa: F401
                              MIN_OCCURRENCES, SUCCESS_FLOOR)


class InMemorySurfacedStore:
    """Offline `do_not_re_surface` marker set. Live swaps a Convex-backed store with the same
    `sig in store` / `store.add(sig)` interface, so surfaced shapes stay surfaced across nightly ticks."""

    def __init__(self, seed=()):
        self._s = set(seed)

    def __contains__(self, sig):
        return sig in self._s

    def add(self, sig):
        self._s.add(sig)

    def all(self):
        return set(self._s)


def _normalize(raw):
    """Accept run-log rows as {"run":…, "seat":…} dicts or (run, seat) tuples → observed signals."""
    obs = []
    for row in raw:
        if isinstance(row, dict) and "run" in row:
            obs.append(observe(row["run"], seat=row.get("seat")))
        elif isinstance(row, (list, tuple)) and len(row) == 2:
            obs.append(observe(row[0], seat=row[1]))
        else:
            raise ValueError(f"run-log row must be {{run,seat}} or (run,seat), got {type(row).__name__}")
    return obs


def _summary(candidates, triaged):
    surfaced = sum(1 for c in candidates if c["decision"] == "surface")
    held = sum(1 for c in candidates if c["decision"] == "hold")
    materialized = sum(1 for d in triaged if d["decision"] == "materialize")
    rejected = sum(1 for d in triaged if d["decision"] == "reject")
    awaiting = sum(1 for d in triaged if d["decision"] == "hold")
    return {"candidates": len(candidates), "surfaced": surfaced, "held": held,
            "materialized": materialized, "rejected": rejected, "awaiting_approval": awaiting}


def run_flywheel_pass(observations, *, existing=(), approvals=None, surfaced=None, emit=None,
                      min_occurrences=MIN_OCCURRENCES, success_floor=SUCCESS_FLOOR):
    """One pass over pre-observed signals. `surfaced` is a PERSISTENT do-not-re-surface store (cross-pass);
    `approvals` maps signature → 'approve'|'reject' (Decision Queue); `emit(spec)` receives each
    materialized scaffold spec (best-effort — an emit error never fails the pass). Returns
    {candidates, triaged, materialized, summary}; held shapes are kept (never silently dropped)."""
    approvals = approvals or {}
    if surfaced is None:
        surfaced = InMemorySurfacedStore()
    candidates = surface(observations, existing=existing, min_occurrences=min_occurrences,
                         success_floor=success_floor)
    triaged, materialized = [], []
    for c in candidates:
        if c["decision"] != "surface":
            continue
        d = triage(c, approval=approvals.get(c["signature"]), surfaced_keys=surfaced)
        triaged.append(d)
        if d["decision"] == "materialize":
            surfaced.add(c["signature"])       # persist so the next tick won't re-surface it
            materialized.append(d)
            if emit is not None:
                try:
                    emit(d["spec"])
                except Exception:
                    pass
    return {"candidates": candidates, "triaged": triaged, "materialized": materialized,
            "summary": _summary(candidates, triaged)}


class FlywheelDriver:
    """Stateful nightly driver over injected seams. `load_runs() -> [rows]`, `load_existing() -> [seats]`
    (or a set), `approvals` (dict or callable) from the Decision Queue, `emit(spec)` sink, and a durable
    `surfaced` store — in-memory offline, Convex/Decision-Queue live."""

    def __init__(self, load_runs, *, load_existing=None, approvals=None, emit=None, surfaced=None,
                 min_occurrences=MIN_OCCURRENCES, success_floor=SUCCESS_FLOOR):
        self.load_runs = load_runs
        self.load_existing = load_existing
        self.approvals = approvals
        self.emit = emit
        self.surfaced = surfaced if surfaced is not None else InMemorySurfacedStore()
        self.min_occurrences = min_occurrences
        self.success_floor = success_floor

    def _existing(self):
        e = self.load_existing() if callable(self.load_existing) else self.load_existing
        return e or ()

    def _approvals(self):
        a = self.approvals() if callable(self.approvals) else self.approvals
        return a or {}

    def tick(self):
        obs = _normalize(self.load_runs() or [])
        return run_flywheel_pass(obs, existing=self._existing(), approvals=self._approvals(),
                                 surfaced=self.surfaced, emit=self.emit,
                                 min_occurrences=self.min_occurrences, success_floor=self.success_floor)
