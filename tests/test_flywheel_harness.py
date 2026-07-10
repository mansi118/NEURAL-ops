"""Flywheel harness tests — one pass over a run corpus (surface/hold/materialize), the emit sink, the
cross-pass do-not-re-surface persistence, and the FlywheelDriver over injected seams. Pure; run:
python3 tests/test_flywheel_harness.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.flywheel import signature  # noqa: E402
from runtime.flywheel_harness import (run_flywheel_pass, FlywheelDriver,  # noqa: E402
                                      InMemorySurfacedStore, _normalize)


def _run(state="DONE", tools=("scrape", "summarize"), phases=("execute", "verify")):
    return {"state": state, "phases": list(phases),
            "events": [{"event": "tool_call", "tool": t} for t in tools]}


RECON_SIG = signature("recon", ["scrape", "summarize"])


def _corpus():
    # recon shape recurs 3x (all DONE) -> eligible; aria shape only twice -> FW-1 hold
    return ([{"run": _run(), "seat": "recon"} for _ in range(3)]
            + [{"run": _run(tools=("draft",)), "seat": "aria"} for _ in range(2)])


def test_surfaces_and_materializes_on_approval():
    emitted = []
    obs = _normalize(_corpus())
    r = run_flywheel_pass(obs, approvals={RECON_SIG: "approve"}, emit=emitted.append)
    assert r["summary"]["surfaced"] == 1 and r["summary"]["held"] == 1, r["summary"]   # recon / aria
    assert r["summary"]["materialized"] == 1, r["summary"]
    spec = r["materialized"][0]["spec"]
    assert spec["neop_id"] == "recon-auto" and spec["role"] == "reactive", spec
    assert emitted == [spec], emitted                                                  # emit sink got it
    print("PASS test_surfaces_and_materializes_on_approval")


def test_no_approval_holds():
    r = run_flywheel_pass(_normalize(_corpus()))          # no approvals -> conservative hold
    assert r["summary"]["materialized"] == 0 and r["summary"]["awaiting_approval"] == 1, r["summary"]
    print("PASS test_no_approval_holds")


def test_existing_catalog_blocks_novelty():
    r = run_flywheel_pass(_normalize(_corpus()), existing={"recon"}, approvals={RECON_SIG: "approve"})
    # FW-3: recon already in the catalog -> held, never materialized
    assert r["summary"]["materialized"] == 0 and r["summary"]["held"] == 2, r["summary"]
    print("PASS test_existing_catalog_blocks_novelty")


def test_cross_pass_do_not_re_surface():
    emitted = []
    corpus = _corpus()
    driver = FlywheelDriver(lambda: corpus, approvals={RECON_SIG: "approve"}, emit=emitted.append)
    r1 = driver.tick()
    r2 = driver.tick()                                     # same corpus, next nightly tick
    assert r1["summary"]["materialized"] == 1, r1["summary"]
    assert r2["summary"]["materialized"] == 0, r2["summary"]     # do-not-re-surface holds across passes
    assert r2["triaged"][0]["decision"] == "reject" and "do_not_re_surface" in r2["triaged"][0]["reason"]
    assert len(emitted) == 1 and RECON_SIG in driver.surfaced, (emitted, driver.surfaced.all())
    print("PASS test_cross_pass_do_not_re_surface")


def test_emit_error_never_fails_pass():
    def boom(_):
        raise RuntimeError("decision queue down")
    r = run_flywheel_pass(_normalize(_corpus()), approvals={RECON_SIG: "approve"}, emit=boom)
    assert r["summary"]["materialized"] == 1, r["summary"]      # spec still materialized despite sink error
    print("PASS test_emit_error_never_fails_pass")


def test_normalize_accepts_tuple_and_dict():
    a = _normalize([{"run": _run(), "seat": "recon"}])
    b = _normalize([(_run(), "recon")])
    assert a == b and a[0]["signature"] == RECON_SIG, (a, b)
    try:
        _normalize(["bad"])
    except ValueError as e:
        assert "run-log row" in str(e)
    else:
        raise AssertionError("expected ValueError on malformed row")
    print("PASS test_normalize_accepts_tuple_and_dict")


def test_driver_seams_callable_or_value():
    corpus = _corpus()
    # load_existing + approvals supplied as callables (live: Convex query / Decision Queue)
    driver = FlywheelDriver(lambda: corpus, load_existing=lambda: [], approvals=lambda: {RECON_SIG: "approve"})
    r = driver.tick()
    assert r["summary"]["materialized"] == 1, r["summary"]
    print("PASS test_driver_seams_callable_or_value")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL FLYWHEEL HARNESS TESTS PASS")
