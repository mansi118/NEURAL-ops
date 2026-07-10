"""Shadow-mode fidelity scorer tests — the layered grader (exact/lexical/judge), the honest
provenance split, and the end-to-end proof that GRADED free-text signals advance the Curator's
fidelity clock (which exact-match `predicted == actual` could not).

Pure logic; core.py untouched; the judge is injected so decisions are deterministic.
Run: python3 tests/test_shadow.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.shadow import (grade, jaccard, shadow_signal, human_signal,  # noqa: E402
                            fidelity_breakdown, signals_from_events, is_shadow_event, recent)
from runtime.curator import curate, fidelity  # noqa: E402


def test_exact_after_normalization():
    # differ only by case/punctuation/whitespace -> exact match on the normalized form
    agreed, score, method = grade("Yes, proceed now!", "yes  proceed now")
    assert agreed is True and method == "exact" and score == 1.0, (agreed, score, method)
    print("PASS test_exact_after_normalization")


def test_lexical_agree_and_disagree():
    # same token set, different order -> jaccard 1.0 (>= 0.6) -> lexical agree (not exact: order differs)
    agreed, score, method = grade("ship it today please", "please ship it today")
    assert agreed is True and method == "lexical" and score == 1.0, (agreed, score, method)
    # disjoint content -> jaccard ~0 (<= 0.1) -> confident lexical disagree, no judge needed
    agreed, score, method = grade("approve the refund", "France is in Europe")
    assert agreed is False and method == "lexical" and score <= 0.1, (agreed, score, method)
    print("PASS test_lexical_agree_and_disagree")


def test_ambiguous_middle_abstains_without_judge():
    # jaccard in the (0.1, 0.6) band and no judge -> UNSCORED (agreed None), never a guess
    agreed, score, method = grade("we should ship it today", "let's ship it tomorrow")
    assert 0.1 < score < 0.6, score
    assert agreed is None and method == "lexical_inconclusive", (agreed, method)
    print("PASS test_ambiguous_middle_abstains_without_judge")


def test_judge_resolves_the_middle():
    pair = ("we should ship it today", "let's ship it tomorrow")
    assert grade(*pair, judge=lambda p, a: 0.8)[0] is True     # judge agrees
    assert grade(*pair, judge=lambda p, a: 0.2)[0] is False    # judge disagrees
    assert grade(*pair, judge=lambda p, a: 5.0)[1] == 1.0      # clamped to [0,1]
    assert grade(*pair, judge=lambda p, a: 0.8)[2] == "judge"  # provenance recorded
    print("PASS test_judge_resolves_the_middle")


def test_missing_side_is_unscored():
    assert grade(None, "hi") == (None, None, "unscored")
    assert grade("hi", None) == (None, None, "unscored")
    print("PASS test_missing_side_is_unscored")


def test_jaccard_edges():
    assert jaccard(set(), set()) == 1.0
    assert jaccard({"a"}, set()) == 0.0
    assert jaccard({"a", "b"}, {"b", "c"}) == 1 / 3
    print("PASS test_jaccard_edges")


def test_signal_shape_matches_curator():
    s = shadow_signal("ship it today", "ship it today", field="tone", kind="additive")
    # carries the fields curator + corroboration read, plus provenance
    for k in ("field", "kind", "agreed", "method", "authoritative", "class"):
        assert k in s, (k, s)
    assert s["agreed"] is True and s["method"] == "exact" and s["authoritative"] is False
    print("PASS test_signal_shape_matches_curator")


def test_breakdown_blended_matches_fidelity_and_splits_human():
    judge = lambda p, a: 0.9  # noqa: E731 — force the ambiguous pair to agree, deterministically
    sigs = [
        shadow_signal("ship it today", "ship it today"),               # exact  -> True
        shadow_signal("approve the refund", "France is in Europe"),    # lexical-> False
        shadow_signal("we should ship it today", "lets ship it soon", judge=judge),  # judge -> True
        human_signal(True),                                            # human  -> True (authoritative)
        human_signal(False),                                           # human  -> False
    ]
    b = fidelity_breakdown(sigs)
    # blended must equal curator.fidelity over the same signals (single source of truth for the rate)
    assert b["blended"] == fidelity(sigs), (b["blended"], fidelity(sigs))
    assert b["blended"] == round(3 / 5, 3), b            # 3 agreed of 5 scored
    assert b["human_only"] == 0.5, b                     # 1 of 2 human labels agreed
    assert b["machine_only"] == round(2 / 3, 3), b       # 2 of 3 machine labels agreed
    assert b["by_method"] == {"exact": 1, "lexical": 1, "judge": 1, "human": 2}, b
    print("PASS test_breakdown_blended_matches_fidelity_and_splits_human")


def test_unscored_never_pollutes_the_rate():
    sigs = [
        shadow_signal("we should ship it today", "let's ship it tomorrow"),  # inconclusive -> None
        shadow_signal("ship it today", "ship it today"),                     # True
    ]
    b = fidelity_breakdown(sigs)
    assert b["n_unscored"] == 1 and b["n_scored"] == 1 and b["blended"] == 1.0, b
    print("PASS test_unscored_never_pollutes_the_rate")


def test_end_to_end_freetext_advances_the_clock():
    """The unlock: graded free-text signals feed the Curator and mature a growing twin — something
    exact-equality (predicted == actual on prose) would never do (it would read ~0.0)."""
    agree_pair = ("please deploy the release now", "deploy the release right now please")  # jaccard .83 -> True
    disagree_pair = ("approve the refund", "penguins waddle across ice")                    # disjoint -> False
    sigs = ([shadow_signal(*agree_pair) for _ in range(70)]
            + [shadow_signal(*disagree_pair) for _ in range(30)])
    # sanity: none of these are exact matches, yet the grader scores them
    assert all(s["method"] != "exact" for s in sigs)
    growing = {"maturity": "growing", "version": 1}
    out = curate(growing, sigs, [], sustained_days=30)
    assert out["fidelity"] == 0.7 and out["maturity"] == "mature", out
    print("PASS test_end_to_end_freetext_advances_the_clock")


def test_event_adapter_filters_and_grades():
    # a mixed run stream: envelope key is 'kind' (core.py) — only shadow_prediction rows are graded
    events = [
        {"kind": "run_start", "neop": "aria"},
        {"kind": "shadow_prediction", "predicted": "ship it today", "actual": "ship it today",
         "agreed": True, "class": "selective"},                        # exact -> True
        {"kind": "memory_write", "status": "ok"},
        {"kind": "shadow_prediction", "predicted": "approve the refund",
         "actual": "penguins waddle across ice", "agreed": False, "class": "reflexive"},  # disjoint -> False
        {"type": "shadow_prediction", "predicted": "deploy the release now",
         "actual": "please deploy the release right now", "class": "selective"},  # 'type' envelope, lexical True
    ]
    sigs = signals_from_events(events)
    assert len(sigs) == 3, sigs                                        # 3 of 5 events are shadow
    assert [s["agreed"] for s in sigs] == [True, False, True], sigs
    assert sigs[1]["class"] == "reflexive", sigs                       # decision class carried through
    assert fidelity(sigs) == round(2 / 3, 3)                           # feeds curator directly
    assert is_shadow_event({"kind": "run_end"}) is False
    print("PASS test_event_adapter_filters_and_grades")


def test_recent_window():
    sigs = [shadow_signal("a", "a") for _ in range(5)]
    assert len(recent(sigs, 2)) == 2 and len(recent(sigs, 0)) == 5 and len(recent(sigs, None)) == 5
    print("PASS test_recent_window")


def test_determinism():
    judge = lambda p, a: 0.7  # noqa: E731
    a = shadow_signal("we should ship it today", "lets ship it soon", judge=judge)
    b = shadow_signal("we should ship it today", "lets ship it soon", judge=judge)
    assert a == b
    print("PASS test_determinism")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL SHADOW TESTS PASS")
