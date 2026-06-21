"""P2 — AwaitingApproval: the approval engine wired into the runtime as a durable pause/resume.
Offline, recorded decide/resolve over the `echo` contract. core.py sanctioned change.
Run: python3 tests/test_awaiting_approval.py

The six acceptance scenarios from the reviewed transition spec:
  1 action grant  2 action deny  3 gate-deny (no pause)  4 hard-deny beats grant
  5 plan grant    6 additive/inert (approval=None and a permissive policy are byte-identical)
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runtime.core import dispatch, dispatch_resume  # noqa: E402
from runtime import approval_gate as AG  # noqa: E402
from acp.approval import ApprovalPolicy  # noqa: E402

ECHO = str(pathlib.Path(__file__).resolve().parents[1] / "agents" / "echo")
CASS = {"plan:x": {"tasks": [{"task_id": "echo", "tool": "echo_tool", "depends_on": []}]},
        "verify:x": {"pass": True}}
MOCKS = {"echo_tool": {"$reflect_field": "text"}}
MSG = {"text": "hi", "tenant": "neuraledge", "seat": "echo"}
RUN_ID = "neuraledge:echo:echo"


def _disp(approval):
    return dispatch(ECHO, MSG, "unit", CASS, MOCKS, [], approval=approval)


def _resume(approval):
    return dispatch_resume(ECHO, RUN_ID, approval, "unit", CASS, MOCKS, [])


def _ev(res, name):
    return [e for e in res["events"] if e["event"] == name]


def test_1_action_grant_pauses_before_mutation_then_resumes_to_done():
    ap = AG.ApprovalBroker(ApprovalPolicy(scope_modes={"plan": "allow", "tool": "ask"}),
                           grants={"echo_tool": "allow"})
    r1 = _disp(ap)
    assert r1["state"] == "AWAITING_APPROVAL", r1["state"]
    aw = _ev(r1, "awaiting_approval")
    assert aw and aw[0]["pause_scope"] == "action"
    assert not _ev(r1, "tool_result")                 # paused BEFORE tools.invoke
    r2 = _resume(ap)
    assert r2["state"] == "DONE", r2["state"]
    assert _ev(r2, "approval_granted")
    assert _ev(r2, "tool_result")                     # the gated tool ran on resume
    print("PASS test_1_action_grant")


def test_2_action_deny_rejects_without_running_tool():
    ap = AG.ApprovalBroker(ApprovalPolicy(scope_modes={"plan": "allow", "tool": "ask"}),
                           grants={"echo_tool": "deny"})
    assert _disp(ap)["state"] == "AWAITING_APPROVAL"
    r2 = _resume(ap)
    assert r2["state"] == "REJECTED", r2["state"]
    assert _ev(r2, "approval_denied")
    assert not _ev(r2, "tool_result")
    print("PASS test_2_action_deny")


def test_3_gate_deny_never_enters_await():
    ap = AG.ApprovalBroker(ApprovalPolicy(scope_modes={"plan": "allow", "tool": "deny"}))
    r1 = _disp(ap)
    assert r1["state"] == "REJECTED", r1["state"]
    assert not _ev(r1, "awaiting_approval")           # AWAIT never entered (deny bypasses the pause)
    assert _ev(r1, "approval_denied")
    try:
        ap.load(RUN_ID); assert False, "no snapshot should be saved on a gate-deny"
    except KeyError:
        pass
    print("PASS test_3_gate_deny_no_pause")


def test_4_hard_deny_beats_grant_on_resume():
    # Pause under a permissive 'ask'; a hard-deny rule is added while paused; the grant can't override it.
    ap = AG.ApprovalBroker(ApprovalPolicy(scope_modes={"plan": "allow", "tool": "ask"}),
                           grants={"echo_tool": "allow"})
    assert _disp(ap)["state"] == "AWAITING_APPROVAL"
    ap.policy.hard_deny.add(("tool", "echo_tool"))    # GW-5 rule added under the pause
    r2 = _resume(ap)
    assert r2["state"] == "REJECTED", r2["state"]
    d = _ev(r2, "approval_denied")
    assert d and "hard_deny" in d[0]["reason"]
    assert not _ev(r2, "tool_result")
    print("PASS test_4_hard_deny_beats_grant")


def test_5_plan_grant_pauses_before_loop_then_done():
    ap = AG.ApprovalBroker(ApprovalPolicy(scope_modes={"plan": "ask", "tool": "allow"}),
                           grants={"plan": "allow"})
    r1 = _disp(ap)
    assert r1["state"] == "AWAITING_APPROVAL"
    aw = _ev(r1, "awaiting_approval")
    assert aw and aw[0]["pause_scope"] == "plan"
    assert not _ev(r1, "tool_call")                   # paused pre-loop, no task started
    r2 = _resume(ap)
    assert r2["state"] == "DONE", r2["state"]
    assert _ev(r2, "tool_result")
    print("PASS test_5_plan_grant")


def test_6_no_policy_and_permissive_policy_are_inert():
    base = _disp(None)
    assert base["state"] == "DONE"
    assert not _ev(base, "awaiting_approval")
    # A policy that ALLOWs everything must add zero events and produce the identical stream.
    ap = AG.ApprovalBroker(ApprovalPolicy(scope_modes={"tool": "allow", "plan": "allow"}))
    perm = _disp(ap)
    assert perm["state"] == "DONE"
    assert [e["event"] for e in perm["events"]] == [e["event"] for e in base["events"]]
    print("PASS test_6_additive_inert")


def test_7_convex_snapshot_store_seam_offline_gradeable():
    """The live paused_runs seam: drop-in for the store, refuses without creds, refuses blank scope —
    no network, nothing faked. Live save/load is gated on Convex paused_runs functions + a deploy."""
    import os
    from runtime.memory import MemPalaceError
    store = AG.ConvexSnapshotStore("palaceX", "seatY")
    ap = AG.ApprovalBroker(ApprovalPolicy(scope_modes={"tool": "ask"}), store=store)
    assert ap.store is store                              # drop-in for MemorySnapshotStore
    saved = dict(os.environ)
    for k in ("CONVEX_DEPLOYMENT_URL", "CONVEX_SITE_URL"):
        os.environ.pop(k, None)
    try:
        try:
            store.save("rid", {"x": 1}); assert False, "must refuse without CONVEX_* creds"
        except MemPalaceError as e:
            assert "not set" in str(e)                    # credential gate, not a network attempt
        try:
            AG.ConvexSnapshotStore("palaceX", "  ").save("rid", {"x": 1}); assert False
        except MemPalaceError as e:
            assert "denied_at_layer=broker" in str(e)     # L4 fail-closed: blank seat refused
    finally:
        os.environ.clear(); os.environ.update(saved)
    print("PASS test_7_convex_snapshot_store_seam")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL AWAITING_APPROVAL TESTS PASS")
