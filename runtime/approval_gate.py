"""Approval gate seam (P2) — the broker the runtime consults at the plan + action gates.

`core.py` stays acp-agnostic: it builds a plain action dict and calls this broker's duck-typed
`decide` / `resolve` / `save` / `load`. This module is the ONLY place that imports `acp.approval`,
so the policy logic (GW-4/5/6, already merged + tested) and the durable-pause store live behind one
seam — recorded/in-memory offline, Convex `paused_runs` live (gated), like every other backend.

Three-way gate (matches `acp.approval.decide`): ALLOW → proceed · AWAIT → pause+snapshot · DENY →
REJECTED (no pause). `resolve` applies a recorded human grant on resume and RE-CHECKS the GW-5
hard-deny — a grant can never override it (the state transitions on the re-checked decision).
"""
from __future__ import annotations

from acp.approval import (Action, ApprovalPolicy, decide as _decide,  # noqa: F401
                          resolve_grant, ALLOW, DENY, AWAIT)

__all__ = ["ApprovalBroker", "MemorySnapshotStore", "ApprovalPolicy"]


class MemorySnapshotStore:
    """Offline snapshot sink (the `paused_runs` seam, unit mode). Live mode swaps this for a
    Convex-backed store with the same save/load interface — pause/resume stays offline-gradeable."""

    def __init__(self):
        self._d = {}

    def save(self, run_id, state):
        self._d[run_id] = state

    def load(self, run_id):
        if run_id not in self._d:
            raise KeyError(f"no paused run {run_id!r}")
        return self._d[run_id]


class ApprovalBroker:
    """Wraps a tenant's ApprovalPolicy + the recorded grants (Decision-Queue resolutions) + the
    snapshot store. `grants` maps an action `name` → "allow" | "deny" (the recorded human verdict
    used on resume); offline it is provided by the fixture, live it is the Decision Queue."""

    def __init__(self, policy, *, grants=None, grantor="ml", store=None):
        self.policy = policy
        self.grants = dict(grants or {})
        self.grantor = grantor
        self.store = store or MemorySnapshotStore()

    def _action(self, d):
        return Action(scope=d["scope"], name=d["name"], seat=d["seat"],
                      tenant=d["tenant"], target=d.get("target"))

    # --- gate (forward pass) -------------------------------------------------
    def decide(self, action):
        """→ (decision, reason). decision ∈ {allow, await, deny}."""
        return _decide(self._action(action), self.policy)

    # --- resolve (resume) ----------------------------------------------------
    def resolve(self, action):
        """Apply the recorded grant on resume. → (decision, reason, grantor). A human ALLOW is
        re-checked against GW-5 hard-deny (resolve_grant); a missing grant is conservatively denied."""
        granted = self.grants.get(action["name"])
        if granted == "deny":
            return DENY, "human_denied_in_decision_queue", self.grantor
        if granted != "allow":
            return DENY, "no_grant_recorded (conservative deny)", self.grantor
        dec, reason = resolve_grant(self._action(action), self.policy, granted_by=self.grantor)
        return dec, reason, self.grantor

    # --- durable pause store -------------------------------------------------
    def save(self, run_id, state):
        self.store.save(run_id, state)

    def load(self, run_id):
        return self.store.load(run_id)
