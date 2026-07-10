"""ApprovalBroker governance-mode tests — ENFORCE stays byte-identical to the raw engine, REPORT_ONLY
proceeds while accumulating shadow decisions, and readiness() summarizes the window. Also the
build_approval `governance` param (distinct from the store `mode`). Pure; run:
python3 tests/test_approval_gate_mode.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from acp.approval import ApprovalPolicy, decide, Action, ALLOW, DENY, AWAIT  # noqa: E402
from runtime.approval_gate import ApprovalBroker, build_approval, ENFORCE, REPORT_ONLY  # noqa: E402

POLICY = ApprovalPolicy(scope_modes={"tool": "ask", "plan": "allow"},
                        overrides={("tool", "curl"): "deny"},
                        hard_deny={("tool", "browser")})


def _a(scope="tool", name="bash"):
    return {"scope": scope, "name": name, "seat": "aria", "tenant": "neuraledge"}


def test_enforce_is_byte_identical():
    b = ApprovalBroker(POLICY)                      # default mode = ENFORCE
    for d in (_a("tool", "bash"), _a("tool", "curl"), _a("tool", "browser"), _a("plan", "x")):
        raw = decide(Action(**d), POLICY)
        assert b.decide(d) == raw, (d, b.decide(d), raw)
    assert b.observed() == [] and b.readiness()["total"] == 0
    print("PASS test_enforce_is_byte_identical")


def test_report_only_proceeds_and_records():
    b = ApprovalBroker(POLICY, mode=REPORT_ONLY)
    # each would be await/deny under enforce, but report-only returns ALLOW and proceeds
    d1, r1 = b.decide(_a("tool", "bash"))           # would await
    d2, r2 = b.decide(_a("tool", "browser"))        # would hard-deny
    d3, r3 = b.decide(_a("plan", "x"))              # would allow
    assert d1 == d2 == d3 == ALLOW, (d1, d2, d3)
    assert "report_only" in r1 and "report_only" in r2
    obs = b.observed()
    assert len(obs) == 3 and [o["would"] for o in obs] == [AWAIT, DENY, ALLOW], obs
    print("PASS test_report_only_proceeds_and_records")


def test_readiness_summarizes_window():
    b = ApprovalBroker(POLICY, mode=REPORT_ONLY)
    for d in (_a("plan", "x"), _a("plan", "y"), _a("tool", "bash"), _a("tool", "curl")):
        b.decide(d)
    r = b.readiness()
    assert r == {"total": 4, "would_allow": 2, "would_deny": 1, "would_await": 1,
                 "block_rate": 0.5}, r
    print("PASS test_readiness_summarizes_window")


def test_bad_mode_rejected():
    try:
        ApprovalBroker(POLICY, mode="observe")
    except ValueError as e:
        assert "unknown governance mode" in str(e)
    else:
        raise AssertionError("expected ValueError")
    print("PASS test_bad_mode_rejected")


def test_build_approval_governance_param():
    cfg = {"scope_modes": {"tool": "ask"}}
    enforced = build_approval(cfg)                                  # default ENFORCE
    observed = build_approval(cfg, governance=REPORT_ONLY)
    assert enforced.mode == ENFORCE and observed.mode == REPORT_ONLY
    # store mode ('unit') and governance are independent knobs
    assert observed.decide(_a("tool", "bash"))[0] == ALLOW          # report-only proceeds
    assert enforced.decide(_a("tool", "bash"))[0] == AWAIT          # enforce pauses
    assert build_approval(None) is None                            # governance OFF unchanged
    print("PASS test_build_approval_governance_param")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL APPROVAL-GATE-MODE TESTS PASS")
