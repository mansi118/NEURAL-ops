"""NEop-spec conformance tests — the agent-patterns classification + gates, enforced in CI.

The headline test lints every shipped NEop (agents/*/) and fails on any error: every NEop must
declare a valid `pattern`, and every `pattern: agent` must carry its stop/feedback gates. The rest are
unit tests of the gate logic. Pure; core.py untouched. Run: python3 tests/test_neop_spec.py
"""
import json
import pathlib
import sys
import tempfile

R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.neop_spec import PATTERN_BY_ROLE, PATTERNS, errors, lint_all, lint_spec, warnings  # noqa: E402

AGENTS = R / "agents"


def _codes(findings):
    return {f["code"] for f in findings}


def _mk(fm: dict, tools=None):
    """Write a temp agents/<x>/ with the given frontmatter (+ optional tools.json)."""
    d = pathlib.Path(tempfile.mkdtemp())
    body = "---\n" + "".join(f"{k}: {json.dumps(v)}\n" for k, v in fm.items()) + "---\n# test\n"
    (d / "neop.md").write_text(body)
    if tools is not None:
        (d / "tools.json").write_text(json.dumps(tools))
    return d


# ── THE enforcement: every shipped NEop conforms ──────────────────────────────
def test_real_agents_all_conformant():
    errs = errors(lint_all(AGENTS))
    assert errs == [], f"non-conformant NEops: {[e['msg'] for e in errs]}"


def test_all_real_agents_declare_a_pattern():
    # no NEop slips through unclassified (G1)
    for folder in sorted(p.parent for p in AGENTS.glob("*/neop.md")):
        assert "missing_pattern" not in _codes(lint_spec(folder)), folder.name


# ── G1: classification required + valid ───────────────────────────────────────
def test_missing_pattern_errors():
    d = _mk({"neop_id": "x", "version": 1, "role_family": "executor", "limits": {"max_replans": 0}})
    assert "missing_pattern" in _codes(errors(lint_spec(d)))


def test_bad_pattern_errors():
    d = _mk({"neop_id": "x", "version": 1, "pattern": "autonomous", "role_family": "meta",
             "limits": {"max_replans": 1}})
    assert "bad_pattern" in _codes(errors(lint_spec(d)))


# ── G2/G3: agent gates ────────────────────────────────────────────────────────
def test_valid_agent_passes():
    d = _mk({"neop_id": "x", "version": 1, "pattern": "agent", "role_family": "meta",
             "limits": {"max_replans": 2}})
    assert errors(lint_spec(d)) == []


def test_agent_without_verify_errors():
    # executor runs EXECUTE only → no environment-feedback verify → can't be an agent (G3)
    d = _mk({"neop_id": "x", "version": 1, "pattern": "agent", "role_family": "executor",
             "limits": {"max_replans": 2}})
    assert "agent_no_verify" in _codes(errors(lint_spec(d)))


def test_agent_unbounded_cap_errors():
    too_big = _mk({"neop_id": "x", "version": 1, "pattern": "agent", "role_family": "meta",
                   "limits": {"max_replans": 999}})
    assert "agent_unbounded" in _codes(errors(lint_spec(too_big)))
    no_cap = _mk({"neop_id": "x", "version": 1, "pattern": "agent", "role_family": "meta",
                  "limits": {}})
    assert "agent_unbounded" in _codes(errors(lint_spec(no_cap)))


# ── simplicity: an augmented_call that pays the pipeline is mislabeled ─────────
def test_augmented_call_overpay_warns():
    d = _mk({"neop_id": "x", "version": 1, "pattern": "augmented_call", "role_family": "meta",
             "limits": {"max_replans": 1}})
    f = lint_spec(d)
    assert errors(f) == [] and "augmented_overpays" in _codes(warnings(f))


def test_clean_augmented_call_passes():
    d = _mk({"neop_id": "x", "version": 1, "pattern": "augmented_call", "role_family": "executor",
             "limits": {"max_replans": 0}}, tools=["t"])
    f = lint_spec(d)
    assert errors(f) == [] and warnings(f) == []


def test_workflow_passes_any_role():
    d = _mk({"neop_id": "x", "version": 1, "pattern": "workflow", "role_family": "meta",
             "limits": {"max_replans": 2}})
    assert errors(lint_spec(d)) == []


# ── G5 (soft): ACI tool surface ───────────────────────────────────────────────
def test_aci_warns_without_tools_json():
    d = _mk({"neop_id": "x", "version": 1, "pattern": "augmented_call", "role_family": "executor",
             "limits": {"max_replans": 0}, "tools": ["sts_whoami"]})  # no tools.json written
    assert "aci_no_tools_json" in _codes(warnings(lint_spec(d)))


# ── both NEop-birth paths agree + carry a valid pattern (no divergent generation path) ────────────
def test_pattern_inference_does_not_drift():
    # canonical (neop_spec) == scaffolder (new_neop) == flywheel — local copies that must never diverge.
    from runtime.flywheel import _PATTERN_BY_ROLE as fw
    from tools.new_neop import _PATTERN_BY_ROLE as nn

    assert fw == PATTERN_BY_ROLE == nn
    assert set(PATTERN_BY_ROLE.values()) <= set(PATTERNS)


def test_flywheel_proposal_carries_valid_pattern():
    # the self-improvement engine must mint specs that would PASS the linter (G1), on every role.
    from runtime.flywheel import _propose

    cases = {("plan", "execute", "verify"): "agent", ("execute", "verify"): "workflow",
             ("execute",): "augmented_call"}
    for phases, expected in cases.items():
        obs = [{"seat": "recon", "tools": ["t"], "phases": phases, "state": "DONE"}]
        proposal = _propose("sig", obs)
        assert proposal["pattern"] == expected and proposal["pattern"] in PATTERNS


if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception:
                traceback.print_exc()
                fails += 1
    raise SystemExit(1 if fails else 0)
