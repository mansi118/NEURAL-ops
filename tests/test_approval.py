"""P2 / GW-4·5·6 — approval mediation policy. Offline, stdlib only. core untouched.
Run: python3 tests/test_approval.py"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from acp import approval as A  # noqa: E402


def _pol(**kw):
    return A.ApprovalPolicy(**kw)


def _act(scope="tool", name="bash", seat="aria", tenant="neuraledge", target=None):
    return A.Action(scope=scope, name=name, seat=seat, tenant=tenant, target=target)


def test_scopes_and_validation():
    assert A.SCOPES == frozenset({"command", "tool", "neop", "plan"})
    for s in A.SCOPES:
        A.Action(scope=s, name="x", seat="a", tenant="t")
    try:
        A.Action(scope="bogus", name="x", seat="a", tenant="t"); assert False
    except A.ApprovalError:
        pass
    print("PASS test_scopes_and_validation")


def test_scope_mode_allow_deny_ask():
    pol = _pol(scope_modes={"tool": "allow", "command": "deny", "neop": "ask"})
    assert A.decide(_act(scope="tool", name="bash"), pol)[0] == A.ALLOW
    assert A.decide(_act(scope="command", name="rm"), pol)[0] == A.DENY
    assert A.decide(_act(scope="neop", name="recon"), pol)[0] == A.AWAIT
    print("PASS test_scope_mode_allow_deny_ask")


def test_unknown_scope_defaults_to_ask():
    pol = _pol()  # nothing configured → conservative default
    assert A.decide(_act(scope="plan", name="deploy"), pol)[0] == A.AWAIT
    print("PASS test_unknown_scope_defaults_to_ask")


def test_override_beats_scope_default():
    pol = _pol(scope_modes={"tool": "allow"}, overrides={("tool", "curl"): "ask"})
    assert A.decide(_act(scope="tool", name="bash"), pol)[0] == A.ALLOW   # scope default
    assert A.decide(_act(scope="tool", name="curl"), pol)[0] == A.AWAIT   # override
    print("PASS test_override_beats_scope_default")


def test_hard_deny_is_non_overridable():
    # Even an explicit override=allow cannot beat the hard-deny (GW-5).
    pol = _pol(scope_modes={"tool": "allow"},
               overrides={("tool", "shell_exec"): "allow"},
               hard_deny={("tool", "shell_exec")})
    d, reason = A.decide(_act(scope="tool", name="shell_exec"), pol)
    assert d == A.DENY and "hard_deny" in reason
    # ...and a human grant cannot override it either.
    gd, greason = A.resolve_grant(_act(scope="tool", name="shell_exec"), pol, granted_by="ml")
    assert gd == A.DENY and "hard_deny" in greason
    print("PASS test_hard_deny_is_non_overridable")


def test_grant_allows_when_not_hard_denied():
    pol = _pol(scope_modes={"plan": "ask"})
    d, _ = A.decide(_act(scope="plan", name="deploy"), pol)
    assert d == A.AWAIT
    gd, greason = A.resolve_grant(_act(scope="plan", name="deploy"), pol, granted_by="ml")
    assert gd == A.ALLOW and "approved_by:ml" in greason
    try:
        A.resolve_grant(_act(scope="plan", name="deploy"), pol, granted_by="  "); assert False
    except A.ApprovalError:
        pass
    print("PASS test_grant_allows_when_not_hard_denied")


def test_audit_record_and_mediate():
    pol = _pol(scope_modes={"tool": "ask"})
    decision, reason, audit = A.mediate(_act(scope="tool", name="bash", target="prod-db"), pol)
    assert decision == A.AWAIT
    for k in ("kind", "scope", "name", "seat", "tenant", "target", "decision", "reason"):
        assert k in audit, k
    assert audit["kind"] == "approval" and audit["target"] == "prod-db" and audit["seat"] == "aria"
    print("PASS test_audit_record_and_mediate")


def test_invalid_mode_rejected():
    try:
        A.ApprovalPolicy(scope_modes={"tool": "maybe"}); assert False
    except A.ApprovalError:
        pass
    print("PASS test_invalid_mode_rejected")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL APPROVAL TESTS PASS")
