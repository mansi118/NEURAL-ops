"""Approval governance mode tests — report-only never blocks but records the shadow decision, enforce
is byte-identical to the raw policy, and flip_readiness summarizes the blast radius. Pure; run:
python3 tests/test_approval_mode.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from acp.approval import Action, ApprovalPolicy, decide, ALLOW, DENY, AWAIT  # noqa: E402
from acp.approval_mode import evaluate, flip_readiness, ENFORCE, REPORT_ONLY  # noqa: E402


def _act(scope="tool", name="bash"):
    return Action(scope=scope, name=name, seat="aria", tenant="neuraledge")


# policy: bash is ask, browser hard-denied, everything else allow-by-scope
POLICY = ApprovalPolicy(scope_modes={"tool": "ask", "plan": "allow"},
                        overrides={("tool", "curl"): "deny"},
                        hard_deny={("tool", "browser")})


def test_enforce_matches_raw_policy():
    for act in (_act("tool", "bash"), _act("tool", "curl"), _act("tool", "browser"), _act("plan", "x")):
        eff, audit = evaluate(act, POLICY, mode=ENFORCE)
        assert eff == decide(act, POLICY)[0], (act, eff)      # byte-identical to the engine
        assert audit["enforced"] is True and audit["mode"] == ENFORCE
    print("PASS test_enforce_matches_raw_policy")


def test_report_only_never_blocks_but_records_would():
    # an action the policy would AWAIT and one it would DENY both PROCEED under report-only
    for act, would in ((_act("tool", "bash"), AWAIT), (_act("tool", "curl"), DENY),
                       (_act("tool", "browser"), DENY)):
        eff, audit = evaluate(act, POLICY, mode=REPORT_ONLY)
        assert eff == ALLOW, (act, eff)                       # nothing blocked while observing
        assert audit["enforced"] is False and audit["would"] == would, audit
        assert audit["decision"] == ALLOW and "report_only" in audit["reason"], audit
    print("PASS test_report_only_never_blocks_but_records_would")


def test_report_only_allow_still_allows():
    eff, audit = evaluate(_act("plan", "x"), POLICY, mode=REPORT_ONLY)  # policy would ALLOW anyway
    assert eff == ALLOW and audit["would"] == ALLOW
    print("PASS test_report_only_allow_still_allows")


def test_flip_readiness_counts_blast_radius():
    audits = [evaluate(a, POLICY, mode=REPORT_ONLY)[1] for a in (
        _act("plan", "x"),        # would allow
        _act("plan", "y"),        # would allow
        _act("tool", "bash"),     # would await
        _act("tool", "curl"),     # would deny
    )]
    r = flip_readiness(audits)
    assert r == {"total": 4, "would_allow": 2, "would_deny": 1, "would_await": 1,
                 "block_rate": 0.5}, r
    print("PASS test_flip_readiness_counts_blast_radius")


def test_flip_readiness_ignores_enforce_and_empty():
    mixed = [evaluate(_act("plan", "x"), POLICY, mode=ENFORCE)[1],   # enforce -> ignored
             evaluate(_act("plan", "x"), POLICY, mode=REPORT_ONLY)[1]]
    assert flip_readiness(mixed)["total"] == 1
    assert flip_readiness([])["block_rate"] is None
    print("PASS test_flip_readiness_ignores_enforce_and_empty")


def test_bad_mode_raises():
    try:
        evaluate(_act(), POLICY, mode="observe")
    except ValueError as e:
        assert "unknown governance mode" in str(e)
    else:
        raise AssertionError("expected ValueError on bad mode")
    print("PASS test_bad_mode_raises")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL APPROVAL-MODE TESTS PASS")
