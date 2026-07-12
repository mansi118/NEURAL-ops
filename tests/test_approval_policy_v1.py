"""approval-policy-v1 artifact tests — the concrete v1 dogfood policy, its loader, and Rego parity.

Verifies the ARTIFACT (not the engine, which is merged + tested in test_approval*.py): the loader
builds a valid ApprovalPolicy, build_approval accepts it (instance + dict, ENFORCE + REPORT_ONLY +
integration), and `acp.approval.decide` / `approval_mode.evaluate` return the decisions the SPEC
(docs/decisions/approval-policy-v1.md) prescribes over a representative action TABLE. If an `opa`
binary is on PATH, the same table is checked against the .rego mirror; otherwise that check SKIPS.

Pure + offline, self-running (repo convention — the CI runner does `python3 tests/<file>.py`; there
is no pytest in CI). Run: python3 tests/test_approval_policy_v1.py
"""
import json
import pathlib
import shutil
import subprocess
import sys

R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))

from acp.approval import Action, ApprovalPolicy, decide, ALLOW, DENY, AWAIT  # noqa: E402
from acp import approval_mode  # noqa: E402
from acp.approval_policy_v1 import DOGFOOD_TENANT, load_policy_v1, policy_config_v1  # noqa: E402
from runtime.approval_gate import build_approval, ApprovalBroker, ENFORCE, REPORT_ONLY  # noqa: E402

REGO = R / "policies" / "approval_policy_v1.rego"
OPERATOR_NEOP = "ml"   # single-grantor dogfood operator (.md §2), passed explicitly at construction.

# ---------------------------------------------------------------------------------------------------
# The action TABLE — every case is drawn from approval-policy-v1.md (§1 tiers / §3 config). Format:
# (scope, name, expected_decision, reason_substr, note-tying-it-to-the-md).
# ---------------------------------------------------------------------------------------------------
TABLE = [
    # ALLOW — reversible, in-tenant, in-scope (§1 ALLOW tier / §3 overrides + neop scope default).
    ("tool", "palace_search",       ALLOW, "policy_allow",  "override: reads / retrieval"),
    ("tool", "palace_remember",     ALLOW, "policy_allow",  "override: in-tenant reversible mutation"),
    ("tool", "palace_get_twin",     ALLOW, "policy_allow",  "override: own-twin (B2 carve-out)"),
    ("tool", "palace_put_twin",     ALLOW, "policy_allow",  "override: own-twin (B2 carve-out)"),
    ("neop", "recon",               ALLOW, "policy_allow",  "scope neop=allow: routing is in-tenant + reversible"),

    # AWAIT — human approval / Decision Queue (§1 AWAIT tier; these inherit the conservative scope 'ask').
    ("tool", "external_send",       AWAIT, "requires_approval", "external send inherits tool scope 'ask'"),
    ("tool", "cross_seat_write",    AWAIT, "requires_approval", "cross-SEAT write inherits tool scope 'ask'"),
    ("tool", "spend_over_floor",    AWAIT, "requires_approval", "spend over a floor inherits tool scope 'ask'"),
    ("plan", "deploy",              AWAIT, "requires_approval", "scope plan=ask: a whole plan pauses once"),
    ("tool", "some_unlisted_tool",  AWAIT, "requires_approval", "long tail inherits default_mode ask (§4)"),

    # DENY — policy (non-hard): raw shell is off by default (§3 scope command=deny).
    ("command", "bash",             DENY,  "policy_deny",   "scope command=deny: raw shell off by default"),

    # DENY — hard, non-overridable GW-5 (§1 DENY tier / §3 hard_deny). A grant can't release these.
    ("tool", "palace_delete",       DENY,  "hard_deny",     "GW-5: data deletion / destructive"),
    ("tool", "cross_tenant_write",  DENY,  "hard_deny",     "GW-5: the isolation boundary itself"),
    ("tool", "secret_read",         DENY,  "hard_deny",     "GW-5: secret access"),
    ("neop", "governance_disable",  DENY,  "hard_deny",     "GW-5: disabling governance"),
    ("tool", "egress_unallowlisted", DENY, "hard_deny",     "GW-5: unallowlisted egress"),
]


def _action(scope, name):
    return Action(scope=scope, name=name, seat="aria", tenant=DOGFOOD_TENANT)


# --- the artifact + loader --------------------------------------------------------------------------
def test_load_policy_v1_is_valid_policy():
    pol = load_policy_v1()
    assert isinstance(pol, ApprovalPolicy)
    assert pol.default_mode == "ask"
    assert pol.scope_modes == {"plan": "ask", "tool": "ask", "neop": "allow", "command": "deny"}
    assert ("tool", "palace_search") in pol.overrides and pol.overrides[("tool", "palace_search")] == "allow"
    assert ("tool", "palace_delete") in pol.hard_deny
    # loader returns a defensive copy — mutating it must not touch the shared artifact.
    cfg = policy_config_v1()
    cfg["scope_modes"]["command"] = "allow"
    assert policy_config_v1()["scope_modes"]["command"] == "deny"
    print("PASS test_load_policy_v1_is_valid_policy")


def test_build_approval_accepts_instance_and_dict():
    # instance path (load_policy_v1) and dict path (policy_config_v1) both construct a broker.
    b_inst = build_approval(load_policy_v1(), grantor=OPERATOR_NEOP)
    b_dict = build_approval(policy_config_v1(), grantor=OPERATOR_NEOP)
    assert isinstance(b_inst, ApprovalBroker) and isinstance(b_dict, ApprovalBroker)
    assert b_inst.mode == ENFORCE and b_inst.grantor == OPERATOR_NEOP
    print("PASS test_build_approval_accepts_instance_and_dict")


def test_build_approval_report_only_and_integration_variants():
    # REPORT_ONLY governance (the observe-before-flip window) constructs and proceeds.
    obs = build_approval(load_policy_v1(), governance=REPORT_ONLY, grantor=OPERATOR_NEOP)
    assert obs.mode == REPORT_ONLY
    assert obs.decide({"scope": "plan", "name": "deploy", "seat": "aria", "tenant": DOGFOOD_TENANT})[0] == ALLOW
    # integration store (per-tenant ConvexSnapshotStore) — needs palace_id, offline at construction.
    integ = build_approval(load_policy_v1(), mode="integration", palace_id="dogfood-palace",
                           grantor=OPERATOR_NEOP)
    assert isinstance(integ, ApprovalBroker)
    # governance OFF is byte-identical to today (dispatch(approval=None)).
    assert build_approval(None) is None
    print("PASS test_build_approval_report_only_and_integration_variants")


# --- the engine over the SPEC's action table --------------------------------------------------------
def test_decide_matches_spec():
    pol = load_policy_v1()
    for scope, name, expected, reason_sub, note in TABLE:
        decision, reason = decide(_action(scope, name), pol)
        assert decision == expected, (scope, name, decision, expected, note)
        assert reason_sub in reason, (scope, name, reason, reason_sub, note)
    print("PASS test_decide_matches_spec")


def test_table_covers_all_three_tiers():
    tiers = {row[2] for row in TABLE}
    assert {ALLOW, DENY, AWAIT} <= tiers
    assert any(r[3] == "hard_deny" for r in TABLE)   # at least one GW-5 hard-deny
    print("PASS test_table_covers_all_three_tiers")


def test_evaluate_enforce_equals_decide():
    # approval_mode.evaluate in ENFORCE = the raw engine decision.
    pol = load_policy_v1()
    for scope, name, expected, reason_sub, note in TABLE:
        eff, audit = approval_mode.evaluate(_action(scope, name), pol, mode=approval_mode.ENFORCE)
        assert eff == expected, (scope, name, eff, expected, note)
        assert audit["enforced"] is True and audit["decision"] == expected
    print("PASS test_evaluate_enforce_equals_decide")


def test_evaluate_report_only_shadows_the_deny():
    # REPORT_ONLY records what it WOULD do but proceeds (effective ALLOW) — even for a hard-deny.
    eff, audit = approval_mode.evaluate(_action("tool", "palace_delete"), load_policy_v1(),
                                        mode=approval_mode.REPORT_ONLY)
    assert eff == ALLOW and audit["enforced"] is False and audit["would"] == DENY
    print("PASS test_evaluate_report_only_shadows_the_deny")


# --- Rego parity (skips cleanly when opa is not on PATH) --------------------------------------------
def _opa_decision(opa, scope, name):
    inp = json.dumps({"scope": scope, "name": name})
    out = subprocess.run(
        [opa, "eval", "-d", str(REGO), "-I", "--format", "json", "data.neos.approval.decision"],
        input=inp, capture_output=True, text=True, check=True)
    doc = json.loads(out.stdout)
    return doc["result"][0]["expressions"][0]["value"]


def test_rego_parity_with_python_engine():
    opa = shutil.which("opa")
    if not opa:
        print("SKIP test_rego_parity_with_python_engine (opa not on PATH — Rego sign-off skipped, not failed)")
        return
    pol = load_policy_v1()
    for scope, name, expected, reason_sub, note in TABLE:
        rego_decision = _opa_decision(opa, scope, name)
        py_decision, _ = decide(_action(scope, name), pol)
        assert rego_decision == py_decision == expected, (scope, name, rego_decision, py_decision, expected)
    print("PASS test_rego_parity_with_python_engine")


if __name__ == "__main__":
    for _n, _f in sorted(globals().items()):
        if _n.startswith("test_") and callable(_f):
            _f()
    print("ALL APPROVAL-POLICY-V1 TESTS PASS")
