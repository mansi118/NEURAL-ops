"""Vault harness (Flow 4 assembly) — drive memory promotion over candidate writes, behind injected seams.

`runtime/vault.py` is the pure five-gate promotion logic (VL1-5) + rollback. This is the driver the
nightly Vault-Promoter cadence runs: it reads candidate writes from the run-log/broker, runs the gates,
and routes promoted records to the durable palace sink — persisting do-not-re-promote ACROSS passes so a
record can't be promoted twice on successive ticks (vault.promote_all only threads that within one batch).
Rollback is exposed and, on success, clears the persistent marker so a corrected record can be re-promoted.

Live swaps the seams: broker.writes / audit run-log for `load_candidates`, the Decision Queue for
`approvals` + `emit`, and a durable marker store for `promoted`. Pure given the seams; timestamps are
INJECTED (`now_ts`), never wall-clock; no I/O here. Conservative posture unchanged — a raw write clears
every gate or it does not durably land.
"""
from __future__ import annotations

from runtime.vault import promote, rollback, CONFIDENCE_FLOORS  # noqa: F401

_EPOCH = "2026-01-01T00:00:00Z"


class InMemoryPromotedStore:
    """Offline do-not-re-promote marker set. Live swaps a Convex-backed store with the same
    `key in store` / `store.add(key)` / `store.discard(key)` interface, so promotions stay durable
    across nightly ticks and a rollback can clear a single key."""

    def __init__(self, seed=()):
        self._s = set(seed)

    def __contains__(self, key):
        return key in self._s

    def add(self, key):
        self._s.add(key)

    def discard(self, key):
        self._s.discard(key)

    def all(self):
        return set(self._s)


def _summary(decisions):
    out = {"candidates": len(decisions), "promoted": 0, "held": 0, "rejected": 0, "redacted": 0}
    for d in decisions:
        out[{"promote": "promoted", "hold": "held", "reject": "rejected"}[d["decision"]]] += 1
        if d["decision"] == "promote" and d["record"].get("pii_redacted"):
            out["redacted"] += 1
    return out


def run_vault_pass(records, *, approvals=None, promoted=None, emit=None, floors=None, now_ts=_EPOCH):
    """One pass over candidate writes. `promoted` is a PERSISTENT do-not-re-promote store (cross-pass);
    `approvals` maps key → 'promote'|'reject' (Decision Queue); `emit(record)` receives each promoted
    (redacted, rollback-armed) record for the durable sink — best-effort, an emit error never fails the
    pass. Returns {decisions, promoted, summary}; held/rejected are kept (never silently dropped)."""
    if promoted is None:
        promoted = InMemoryPromotedStore()
    decisions, landed = [], []
    for r in records:
        d = promote(r, approvals=approvals, promoted_keys=promoted, floors=floors, now_ts=now_ts)
        decisions.append(d)
        if d["decision"] == "promote":
            promoted.add(d["key"])            # persist so the next tick won't re-promote it
            landed.append(d)
            if emit is not None:
                try:
                    emit(d["record"])
                except Exception:
                    pass
    return {"decisions": decisions, "promoted": landed, "summary": _summary(decisions)}


class VaultPromoter:
    """Stateful nightly driver over injected seams. `load_candidates() -> [records]`, `approvals`
    (dict or callable) from the Decision Queue, `emit(record)` durable sink, and a durable `promoted`
    store — in-memory offline, Convex/Decision-Queue live."""

    def __init__(self, load_candidates, *, approvals=None, emit=None, promoted=None, floors=None,
                 now_ts=_EPOCH):
        self.load_candidates = load_candidates
        self.approvals = approvals
        self.emit = emit
        self.promoted = promoted if promoted is not None else InMemoryPromotedStore()
        self.floors = floors
        self.now_ts = now_ts

    def _approvals(self):
        a = self.approvals() if callable(self.approvals) else self.approvals
        return a or {}

    def tick(self, *, now_ts=None):
        return run_vault_pass(self.load_candidates() or [], approvals=self._approvals(),
                              promoted=self.promoted, emit=self.emit, floors=self.floors,
                              now_ts=now_ts or self.now_ts)

    def rollback(self, record, *, now_ts=None):
        """VL-5 reversal — retract a promoted record within its TTL and, on success, clear its marker so
        a corrected version can be re-promoted (mirrors vault.rollback.clear_do_not_re_promote)."""
        d = rollback(record, now_ts=now_ts or self.now_ts)
        if d["decision"] == "rollback" and d.get("clear_do_not_re_promote"):
            self.promoted.discard(d["key"])
        return d
