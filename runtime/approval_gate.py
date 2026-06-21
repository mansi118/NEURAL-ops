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

__all__ = ["ApprovalBroker", "MemorySnapshotStore", "ConvexSnapshotStore", "ApprovalPolicy"]


class MemorySnapshotStore:
    """Offline snapshot sink (the `paused_runs` seam, unit mode). Live mode swaps this for a
    Convex-backed store with the same save/load/resolve/pending interface — the Decision Queue
    (pending pauses) and resume→resolved lifecycle stay offline-gradeable."""

    def __init__(self):
        self._d = {}                       # run_id -> {state, status}

    def save(self, run_id, state):
        self._d[run_id] = {"state": state, "status": "pending"}

    def load(self, run_id):
        if run_id not in self._d:
            raise KeyError(f"no paused run {run_id!r}")
        return self._d[run_id]["state"]

    def resolve(self, run_id, status="resolved"):
        if run_id in self._d:
            self._d[run_id]["status"] = status

    def pending(self):
        """The Decision Queue: run_ids still awaiting a human (offline mirror of pendingPausedRuns)."""
        return [rid for rid, v in self._d.items() if v["status"] == "pending"]


class ConvexSnapshotStore:
    """Live `paused_runs` seam — PER-TENANT durable snapshot store over the Convex SoT, a drop-in for
    MemorySnapshotStore. Reuses `runtime.memory._post` (so it inherits the credential gate + the L4
    fail-closed scope guard) and only touches the network when a live deployment is configured.

    Grain aligned to the per-tenant ApprovalBroker: **palaceId is baked (the tenant); per-run scope
    (neopId) is NOT baked — it is provenance**:
      - save   writes the row under the snapshot's OWN seat (`state["seat"]`) — the row records who paused.
      - load / resolve key by (palaceId, runId); the SERVER reads neopId FROM the row (`by_palace_run`),
        NEVER from the caller. So "resume this paused run" can't become "resume any run I name" — the
        caller supplies only runId; the scope is the row's, server-written at save. Same provenance-
        not-assertion invariant as the twin keying. `operator_neop` is the load/resolve envelope identity
        (the resume/operator context) — it satisfies the perm gate, it does NOT key the row."""

    SAVE_TOOL = "palace_save_paused_run"
    LOAD_TOOL = "palace_get_paused_run"
    RESOLVE_TOOL = "palace_resolve_paused_run"

    def __init__(self, palace_id, *, operator_neop="_admin"):
        self.palace_id = palace_id
        self.operator_neop = operator_neop

    def save(self, run_id, state):
        from runtime.memory import _post   # lazy: import cost + credential gate only on live use
        seat = (state or {}).get("seat")    # provenance — the row records the seat that paused
        _post(self.SAVE_TOOL, self.palace_id, seat, {"runId": run_id, "state": state})

    def load(self, run_id):
        from runtime.memory import _post
        # keyed by (palaceId, runId); the server reads neopId FROM the row — caller can't substitute scope.
        data = _post(self.LOAD_TOOL, self.palace_id, self.operator_neop, {"runId": run_id})
        state = data.get("state") if isinstance(data, dict) else None
        if state is None:
            raise KeyError(f"no paused run {run_id!r} in Convex paused_runs")
        return state

    def resolve(self, run_id, status="resolved"):
        from runtime.memory import _post
        _post(self.RESOLVE_TOOL, self.palace_id, self.operator_neop, {"runId": run_id, "status": status})


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

    def mark_resolved(self, run_id, terminal_state):
        """Decision Queue lifecycle: a resumed pause is no longer pending. REJECTED → denied, else
        resolved. Best-effort — callers wrap this so a store hiccup never fails the resume."""
        status = "denied" if terminal_state == "REJECTED" else "resolved"
        self.store.resolve(run_id, status)

    def pending(self):
        return self.store.pending()
