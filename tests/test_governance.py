"""Governance factory tests — approval-policy-v1 as a config flip (Track 1).

OFF (default) returns None (byte-identical, governance inert); report_only builds a broker that PROCEEDS
but records the shadow decision; the ENFORCE flip is GATED behind an explicit ack; the grantor is required
and never baked. Pure; no network. Run: python3 tests/test_governance.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.governance import approval_from_env  # noqa: E402
from runtime.approval_gate import ApprovalBroker, ConvexSnapshotStore, ENFORCE, REPORT_ONLY  # noqa: E402
from acp.approval import ALLOW  # noqa: E402


def test_off_or_unset_returns_none():
    for env in ({}, {"NEOS_GOVERNANCE": "off"}, {"NEOS_GOVERNANCE": ""}, {"NEOS_GOVERNANCE": "no"}):
        assert approval_from_env(env) is None, env
    print("PASS test_off_or_unset_returns_none")


def test_report_only_builds_a_proceeding_broker():
    b = approval_from_env({"NEOS_GOVERNANCE": "report_only", "NEOS_GOVERNANCE_GRANTOR": "ml"})
    assert isinstance(b, ApprovalBroker)
    assert b.mode == REPORT_ONLY
    assert b.grantor == "ml"
    # report-only NEVER blocks: even a would-deny action proceeds as ALLOW, and it is recorded for readiness.
    decision, _ = b.decide({"scope": "tool", "name": "browser", "seat": "aria", "tenant": "neuraledge"})
    assert decision == ALLOW
    assert len(b.observed()) == 1
    assert b.readiness()["total"] == 1
    print("PASS test_report_only_builds_a_proceeding_broker")


def test_grantor_required_when_on():
    for env in ({"NEOS_GOVERNANCE": "report_only"},
                {"NEOS_GOVERNANCE": "report_only", "NEOS_GOVERNANCE_GRANTOR": "   "}):
        try:
            approval_from_env(env)
        except ValueError as e:
            assert "GRANTOR" in str(e)
        else:
            raise AssertionError("expected ValueError on blank grantor")
    print("PASS test_grantor_required_when_on")


def test_enforce_is_gated_without_ack():
    try:
        approval_from_env({"NEOS_GOVERNANCE": "enforce", "NEOS_GOVERNANCE_GRANTOR": "ml"})
    except RuntimeError as e:
        assert "REFUSING to enforce" in str(e) and "NEOS_GOVERNANCE_ENFORCE_ACK" in str(e)
    else:
        raise AssertionError("enforce without ack must refuse (the flip is gated)")
    print("PASS test_enforce_is_gated_without_ack")


def test_enforce_with_ack_builds_enforcing_broker():
    b = approval_from_env({"NEOS_GOVERNANCE": "enforce", "NEOS_GOVERNANCE_GRANTOR": "ml",
                           "NEOS_GOVERNANCE_ENFORCE_ACK": "yes"})
    assert isinstance(b, ApprovalBroker) and b.mode == ENFORCE
    # ENFORCE is the real gate: a hard-denied action is actually denied (not ALLOW).
    decision, _ = b.decide({"scope": "tool", "name": "browser", "seat": "aria", "tenant": "neuraledge"})
    assert decision != ALLOW
    print("PASS test_enforce_with_ack_builds_enforcing_broker")


def test_bad_setting_and_bad_store_raise():
    try:
        approval_from_env({"NEOS_GOVERNANCE": "observe", "NEOS_GOVERNANCE_GRANTOR": "ml"})
    except ValueError as e:
        assert "off|report_only|enforce" in str(e)
    else:
        raise AssertionError("expected ValueError on unknown governance setting")
    try:
        approval_from_env({"NEOS_GOVERNANCE": "report_only", "NEOS_GOVERNANCE_GRANTOR": "ml",
                           "NEOS_GOVERNANCE_STORE": "integration"})  # no PALACE_ID
    except ValueError as e:
        assert "PALACE_ID" in str(e)
    else:
        raise AssertionError("integration store without PALACE_ID must raise")
    print("PASS test_bad_setting_and_bad_store_raise")


def test_integration_store_with_palace_id_builds_offline():
    b = approval_from_env({"NEOS_GOVERNANCE": "report_only", "NEOS_GOVERNANCE_GRANTOR": "ml",
                           "NEOS_GOVERNANCE_STORE": "integration", "PALACE_ID": "pal_123"})
    assert isinstance(b, ApprovalBroker)
    assert isinstance(b.store, ConvexSnapshotStore)   # no network at construction (credential-gated on use)
    assert b.store.palace_id == "pal_123"
    print("PASS test_integration_store_with_palace_id_builds_offline")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL GOVERNANCE TESTS PASS")
