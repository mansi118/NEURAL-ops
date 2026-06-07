"""Twin Curator (Flow 6) tests — fidelity, corroboration (incl. the conservative no-op),
lifecycle transitions AND the holds, version-bump-vs-buffer, determinism.

Pure logic; core.py untouched. The curator takes an injected `sustained_days` (no
wall-clock), so decisions are deterministic. Run: python3 tests/test_curator.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.curator import curate, fidelity, corroborated  # noqa: E402

SEED = {"twin_id": "neuraledge:aria", "maturity": "seed", "version": 0}


def _sig(field="decision_style", kind="structural", agreed=True, n=1):
    return [{"field": field, "kind": kind, "agreed": agreed} for _ in range(n)]


def test_fidelity_exact():
    s = [{"agreed": True}, {"agreed": True}, {"agreed": True}, {"agreed": False}, {"agreed": None}]
    assert fidelity(s) == 0.75, fidelity(s)          # 3 agreed of 4 scored; None ignored
    assert fidelity([]) is None
    print("PASS test_fidelity_exact")


def test_corroboration_threshold_and_noop():
    assert corroborated({"field": "x", "kind": "structural"}, _sig("x", n=3))[0] is True
    assert corroborated({"field": "x", "kind": "structural"}, _sig("x", n=2))[0] is False   # <3 -> no-op
    assert corroborated({"field": "x", "kind": "additive"}, _sig("x", n=1))[0] is True
    assert corroborated({"field": "x", "kind": "additive"}, [])[0] is False                  # 0 -> no-op
    # the no-op is EXPLICIT: an uncorroborated edit must not mutate the twin
    r = curate(SEED, _sig("decision_style", n=2),
               [{"field": "decision_style", "value": "v", "kind": "structural"}])
    assert r["buffered"] and not r["committed"] and r["twin"].get("decision_style") != "v", r
    print("PASS test_corroboration_threshold_and_noop")


def test_seed_to_growing_and_hold():
    assert curate(SEED, _sig(n=3), [])["maturity"] == "growing"   # first corroborated signals
    assert curate(SEED, _sig(n=2), [])["maturity"] == "seed"      # <3 structural -> stays seed
    print("PASS test_seed_to_growing_and_hold")


def test_growing_to_mature_and_holds():
    g = {"maturity": "growing", "version": 1}
    assert curate(g, _sig(agreed=True, n=70) + _sig(agreed=False, n=30), [], sustained_days=30)["maturity"] == "mature"
    # HOLD 1: fidelity 0.64 (< 0.65) stays growing even at 30d
    assert curate(g, _sig(agreed=True, n=64) + _sig(agreed=False, n=36), [], sustained_days=30)["maturity"] == "growing"
    # HOLD 2: fidelity 0.66 but only 20d -> gate must not fire early
    assert curate(g, _sig(agreed=True, n=66) + _sig(agreed=False, n=34), [], sustained_days=20)["maturity"] == "growing"
    print("PASS test_growing_to_mature_and_holds")


def test_drift_and_retune_and_holds():
    m = {"maturity": "mature", "version": 5}
    assert curate(m, [], [], overrides=3)["maturity"] == "drifted"   # repeated overrides
    assert curate(m, [], [], overrides=2)["maturity"] == "mature"    # HOLD: not enough overrides
    d = {"maturity": "drifted", "version": 6}
    assert curate(d, [], [], retune_accepted=True)["maturity"] == "growing"
    assert curate(d, [], [], retune_accepted=False)["maturity"] == "drifted"  # HOLD: no re-tune
    print("PASS test_drift_and_retune_and_holds")


def test_version_bump_vs_buffer():
    g = {"maturity": "growing", "version": 3}
    c = curate(g, _sig("a", n=3), [{"field": "a", "value": "x", "kind": "structural"}])
    assert c["twin"]["version"] == 4 and c["twin"]["a"] == "x", c        # committed -> bump
    b = curate(g, _sig("a", n=1), [{"field": "a", "value": "y", "kind": "structural"}])
    assert b["twin"]["version"] == 3 and b["twin"].get("a") != "y" and b["buffered"], b  # buffer -> no bump
    print("PASS test_version_bump_vs_buffer")


def test_determinism():
    sig, edits = _sig(n=3), [{"field": "a", "value": "x", "kind": "structural"}]
    assert curate(SEED, sig, edits) == curate(SEED, sig, edits)   # same stream -> same decision
    print("PASS test_determinism")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL CURATOR TESTS PASS")
