"""LLM-as-judge tests — prompt shape, robust score parsing, the abstain-on-failure contract, and the
end-to-end plug into shadow.grade. The model call is an injected stub, so decisions are deterministic.

Run: python3 tests/test_judge.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.judge import judge_prompt, parse_judge_score, make_judge  # noqa: E402
from runtime.shadow import grade  # noqa: E402


def test_prompt_contains_both_sides_and_asks_for_json():
    p = judge_prompt("ship it", "hold off")
    assert "PROPOSED:\nship it" in p and "ACTUAL:\nhold off" in p, p
    assert '"score"' in p, p
    print("PASS test_prompt_contains_both_sides_and_asks_for_json")


def test_parse_variants():
    assert parse_judge_score('{"score": 0.8}') == 0.8
    assert parse_judge_score('{"agreement": 0.7, "why": "x"}') == 0.7   # alt key, extra field ignored
    assert parse_judge_score("0.65") == 0.65
    assert parse_judge_score("Score: 80%") == 0.8                       # percent
    assert parse_judge_score("1.5") == 1.0                              # overshoot clamps to max
    assert parse_judge_score("-0.2") == 0.0                             # negative clamps to min
    assert parse_judge_score('{"score": true}') is None                # bool is not a score
    assert parse_judge_score("") is None and parse_judge_score("n/a") is None
    print("PASS test_parse_variants")


def test_make_judge_happy_path():
    j = make_judge(lambda prompt: '{"score": 0.9}')
    assert j("a", "b") == 0.9
    print("PASS test_make_judge_happy_path")


def test_make_judge_abstains_on_error_and_garbage():
    def boom(_):
        raise RuntimeError("model down")
    assert make_judge(boom)("a", "b") is None          # model error -> abstain
    assert make_judge(lambda p: "sorry i can't")("a", "b") is None   # unparseable -> abstain
    print("PASS test_make_judge_abstains_on_error_and_garbage")


def test_plugs_into_shadow_grade():
    pair = ("we should ship it today", "let's ship it tomorrow")  # ambiguous middle -> judge consulted
    agree_judge = make_judge(lambda p: '{"score": 0.85}')
    abstain_judge = make_judge(lambda p: "who knows")
    assert grade(*pair, judge=agree_judge) == (True, 0.85, "judge")
    # abstain -> UNSCORED, provenance judge_abstain (shadow.grade honesty contract)
    agreed, score, method = grade(*pair, judge=abstain_judge)
    assert agreed is None and method == "judge_abstain", (agreed, method)
    print("PASS test_plugs_into_shadow_grade")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL JUDGE TESTS PASS")
