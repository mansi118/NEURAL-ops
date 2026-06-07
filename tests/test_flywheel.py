"""Automation flywheel (Flow 8) tests — observe->surface->approve->NEop.

Five gates AND every HOLD/refuse: under-recurrence holds, a flaky shape holds, a shape that
already exists holds, no-approval holds + reject rejects, approve emits a SPEC (never an agent),
re-surface is refused, and the whole pass is deterministic. Pure logic; core.py untouched.
Run: python3 tests/test_flywheel.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.flywheel import observe, surface, triage, run_flywheel  # noqa: E402


def _run(seat, tools, state="DONE", phases=("plan", "execute", "verify")):
    events = [{"event": "tool_call", "tool": t} for t in tools]
    return observe({"state": state, "phases": list(phases), "events": events}, seat=seat)


def _corpus(n, **kw):
    return [_run(**kw) for _ in range(n)]


def test_observe_signature():
    o = _run("recon", ["search_leads", "enrich_lead"])
    assert o["signature"] == "recon|search_leads,enrich_lead" and o["tools"] == ["search_leads", "enrich_lead"], o
    # tool spine comes from tool_call events in order; phases captured for role inference
    assert o["phases"] == ("plan", "execute", "verify") and o["state"] == "DONE", o
    print("PASS test_observe_signature")


def test_fw1_recurrence_floor():
    s = surface(_corpus(3, seat="x", tools=["a"]))           # exactly the floor -> surfaces
    assert s[0]["decision"] == "surface" and s[0]["gates"]["FW-1"] == "pass", s
    h = surface(_corpus(2, seat="x", tools=["a"]))           # below floor -> HOLD (not enough evidence)
    assert h[0]["decision"] == "hold" and "FW-1" in h[0]["reason"], h
    print("PASS test_fw1_recurrence_floor")


def test_fw2_success_bias():
    # 4 of 6 DONE = 0.667 >= 0.6 -> surfaces; 3 of 6 = 0.5 < 0.6 -> HOLD (too flaky to automate)
    good = _corpus(4, seat="y", tools=["a"]) + _corpus(2, seat="y", tools=["a"], state="ESCALATED")
    assert surface(good)[0]["decision"] == "surface", surface(good)
    flaky = _corpus(3, seat="y", tools=["a"]) + _corpus(3, seat="y", tools=["a"], state="FAILED")
    f = surface(flaky)[0]
    assert f["decision"] == "hold" and "FW-2" in f["reason"], f
    print("PASS test_fw2_success_bias")


def test_fw3_novelty():
    s = surface(_corpus(3, seat="recon", tools=["a"]), existing=["recon"])  # already in catalog
    assert s[0]["decision"] == "hold" and "FW-3" in s[0]["reason"], s
    assert surface(_corpus(3, seat="recon", tools=["a"]), existing=["other"])[0]["decision"] == "surface"
    print("PASS test_fw3_novelty")


def test_role_inference():
    meta = surface(_corpus(3, seat="m", tools=["a"], phases=("plan", "execute", "verify")))[0]
    react = surface(_corpus(3, seat="r", tools=["a"], phases=("execute", "verify")))[0]
    exec_ = surface(_corpus(3, seat="e", tools=["a"], phases=("execute",)))[0]
    assert meta["proposal"]["role"] == "meta", meta
    assert react["proposal"]["role"] == "reactive", react
    assert exec_["proposal"]["role"] == "executor", exec_
    print("PASS test_role_inference")


def test_fw4_approval_and_consent():
    c = surface(_corpus(3, seat="z", tools=["a"]))[0]
    assert triage(c)["decision"] == "hold" and triage(c)["gates"]["FW-4"] == "needs_review"   # no approval
    assert triage(c, approval="reject")["decision"] == "reject"                               # explicit reject
    assert triage(c, approval="approve")["decision"] == "materialize"                         # explicit consent
    print("PASS test_fw4_approval_and_consent")


def test_fw5_spec_only_and_no_resurface():
    c = surface(_corpus(3, seat="z", tools=["search", "rank"]))[0]
    d = triage(c, approval="approve")
    # FW-5: emits a SCAFFOLD SPEC for a human to run — it does NOT spawn an agent
    assert d["decision"] == "materialize" and d["gates"]["FW-5"] == "spec_only", d
    assert d["spec"]["neop_id"] == "z-auto" and d["spec"]["tools"] == ["search", "rank"], d
    assert "tools/new_neop.py z-auto" in d["spec"]["scaffold_cmd"], d
    # do-not-re-surface: the same signature can't be surfaced twice
    again = triage(c, approval="approve", surfaced_keys={c["signature"]})
    assert again["decision"] == "reject" and "FW-5" in again["reason"], again
    print("PASS test_fw5_spec_only_and_no_resurface")


def test_run_flywheel_threads_no_resurface():
    # two identical-signature batches in one pass: a single materialize, never two.
    corpus = _corpus(6, seat="dup", tools=["a"])
    cands, triaged = run_flywheel(corpus, approvals={"dup|a": "approve"})
    mats = [t for t in triaged if t["decision"] == "materialize"]
    assert len(cands) == 1 and len(mats) == 1, (cands, triaged)
    # a held shape is still reported by surface() (never silently dropped)
    cands2, _ = run_flywheel(_corpus(2, seat="dup", tools=["a"]))
    assert cands2[0]["decision"] == "hold", cands2
    print("PASS test_run_flywheel_threads_no_resurface")


def test_determinism():
    corpus = _corpus(3, seat="z", tools=["a", "b"]) + _corpus(3, seat="w", tools=["c"])
    assert run_flywheel(corpus) == run_flywheel(corpus)            # same corpus -> same decision
    # candidates are sorted by signature -> stable order regardless of input order
    assert [c["signature"] for c in surface(corpus)] == sorted(c["signature"] for c in surface(corpus))
    print("PASS test_determinism")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL FLYWHEEL TESTS PASS")
