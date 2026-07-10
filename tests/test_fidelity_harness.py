"""Fidelity harness tests — the one-pass fold (events -> graded signals -> curate) and the stateful
FidelityLoop over injected seams (persist-on-change, no-op writes nothing). Stubs for judge + I/O
keep it deterministic and offline. Run: python3 tests/test_fidelity_harness.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.fidelity_harness import run_fidelity_pass, should_persist, FidelityLoop  # noqa: E402
from runtime.judge import make_judge  # noqa: E402


def _shadow(pred, actual, cls="selective"):
    return {"kind": "shadow_prediction", "predicted": pred, "actual": actual, "class": cls}


# 70 lexical-agree + 30 disjoint-disagree finished-run events (free text, none exact matches)
def _traffic():
    agree = _shadow("please deploy the release now", "deploy the release right now please")
    disagree = _shadow("approve the refund", "penguins waddle across ice")
    return [dict(agree) for _ in range(70)] + [dict(disagree) for _ in range(30)]


def test_pass_grades_and_matures():
    growing = {"maturity": "growing", "version": 1}
    r = run_fidelity_pass(_traffic(), growing, sustained_days=30)
    assert r["fidelity"] == 0.7 and r["maturity"] == "mature", r
    assert r["scored"] == 100 and r["breakdown"]["blended"] == 0.7, r["breakdown"]
    print("PASS test_pass_grades_and_matures")


def test_window_bounds_volume():
    growing = {"maturity": "growing", "version": 1}
    r = run_fidelity_pass(_traffic(), growing, window=30, sustained_days=30)
    # last 30 events are all the disagree row -> fidelity 0.0, stays growing
    assert r["scored"] == 30 and r["fidelity"] == 0.0 and r["maturity"] == "growing", r
    print("PASS test_window_bounds_volume")


def test_should_persist_rules():
    old = {"signals": {"agreement_rate_30d": 0.5}}
    assert should_persist(old, {"transitioned": True, "committed": [], "fidelity": 0.5}) is True
    assert should_persist(old, {"transitioned": False, "committed": ["x"], "fidelity": 0.5}) is True
    assert should_persist(old, {"transitioned": False, "committed": [], "fidelity": 0.7}) is True  # score moved
    assert should_persist(old, {"transitioned": False, "committed": [], "fidelity": 0.5}) is False  # no-op
    print("PASS test_should_persist_rules")


def test_loop_persists_on_change():
    store = {}
    saved = []
    def load_twin(t, s): return store.get((t, s))
    def save_twin(t, s, twin): store[(t, s)] = twin; saved.append((t, s, twin["version"]))
    def load_events(t, s): return _traffic()

    loop = FidelityLoop(load_twin, save_twin, load_events)
    store[("neuraledge", "aria")] = {"maturity": "growing", "version": 1}
    r = loop.tick("neuraledge", "aria", sustained_days=30)
    assert r["maturity"] == "mature" and r["persisted"] is True and len(saved) == 1, (r, saved)
    assert store[("neuraledge", "aria")]["version"] == 2, store  # transition bumped the version
    print("PASS test_loop_persists_on_change")


def test_loop_noop_writes_nothing():
    saved = []
    def load_twin(t, s): return {"maturity": "seed", "version": 0}
    def save_twin(t, s, twin): saved.append((t, s))
    def load_events(t, s): return []              # no traffic -> no signals -> nothing changes

    loop = FidelityLoop(load_twin, save_twin, load_events)
    r = loop.tick("neuraledge", "recon")
    assert r["persisted"] is False and saved == [], (r["persisted"], saved)
    assert r["maturity"] == "seed" and r["fidelity"] is None, r
    print("PASS test_loop_noop_writes_nothing")


def test_loop_uses_injected_judge_on_ambiguous():
    # ambiguous-middle events (jaccard in the band) -> only a judge can SCORE them. (The seed->growing
    # count is a separate curator rule; here we isolate that the judge changes what gets scored.)
    def load_events(t, s): return [_shadow("we should ship it today", "lets ship it soon")
                                   for _ in range(3)]
    def load_twin(t, s): return {"maturity": "growing", "version": 1}
    def save_twin(t, s, twin): pass

    # no judge -> all unscored -> fidelity is None (nothing to rate)
    r0 = FidelityLoop(load_twin, save_twin, load_events).tick("t", "s", sustained_days=30)
    assert r0["scored"] == 0 and r0["fidelity"] is None, r0
    # with an agreeing judge -> 3 scored signals, fidelity 1.0
    judge = make_judge(lambda p: '{"score": 0.9}')
    r1 = FidelityLoop(load_twin, save_twin, load_events, judge=judge).tick("t", "s", sustained_days=30)
    assert r1["scored"] == 3 and r1["fidelity"] == 1.0, r1
    print("PASS test_loop_uses_injected_judge_on_ambiguous")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL FIDELITY HARNESS TESTS PASS")
