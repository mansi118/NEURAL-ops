"""runtime.bedrock — Converse invoke (Claude Haiku default) request BUILDER + response PARSER, offline.

Injects a fake `transport` so no network is touched: asserts the /converse URL + model id, the bearer
header, the Converse body shape (messages/inferenceConfig/system), text extraction, the Haiku default,
and that EVERY failure (blank bearer, transport error, bad shape) raises a NAMED BedrockError — which is
what lets `make_judge` abstain rather than fabricate a grade.

Self-running (repo convention — CI runs `python3 tests/<f>.py`, no pytest). Run: python3 tests/test_bedrock.py
"""
import json
import os
import pathlib
import sys

R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))

from runtime.bedrock import bedrock_converse, converse_invoke, BedrockError, DEFAULT_JUDGE_MODEL  # noqa: E402
from runtime.judge import make_judge  # noqa: E402

HAIKU = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


def _ok(text):
    """A fake transport returning a well-formed Converse envelope carrying `text`."""
    def _t(url, headers, body, timeout):
        _t.seen = {"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout}
        return json.dumps({"output": {"message": {"content": [{"text": text}]}}})
    return _t


def test_converse_builds_request_and_parses():
    t = _ok("  0.8  ")
    out = bedrock_converse("grade this", model_id=HAIKU, bearer="tok", system="sys", transport=t)
    assert out == "0.8", out                                   # extracted + trimmed
    assert "/converse" in t.seen["url"] and "claude-haiku" in t.seen["url"], t.seen["url"]
    assert t.seen["url"].startswith("https://bedrock-runtime.ap-south-1."), t.seen["url"]
    assert t.seen["headers"]["Authorization"] == "Bearer tok"
    b = t.seen["body"]
    assert b["messages"][0]["content"][0]["text"] == "grade this"
    assert b["system"][0]["text"] == "sys"
    assert b["inferenceConfig"]["temperature"] == 0.0
    print("PASS test_converse_builds_request_and_parses")


def test_converse_invoke_defaults_to_haiku():
    os.environ.pop("FIDELITY_JUDGE_MODEL", None)              # no override → the Claude Haiku default
    t = _ok("ok")
    inv = converse_invoke(bearer="tok", transport=t)
    assert inv("hi") == "ok"
    assert DEFAULT_JUDGE_MODEL == HAIKU
    assert HAIKU in t.seen["url"], t.seen["url"]
    print("PASS test_converse_invoke_defaults_to_haiku")


def test_converse_invoke_honors_model_override():
    t = _ok("ok")
    inv = converse_invoke(model_id="global.anthropic.claude-sonnet-4-5-20250929-v1:0", bearer="tok", transport=t)
    inv("hi")
    assert "claude-sonnet" in t.seen["url"], t.seen["url"]
    print("PASS test_converse_invoke_honors_model_override")


def test_blank_bearer_is_fail_closed():
    try:
        bedrock_converse("x", model_id=HAIKU, bearer="", transport=_ok("nope"))
        assert False, "blank bearer must raise"
    except BedrockError as e:
        assert "blank" in str(e).lower() or "fail-closed" in str(e).lower(), str(e)
    print("PASS test_blank_bearer_is_fail_closed")


def test_transport_error_raises_named():
    def boom(url, headers, body, timeout):
        raise RuntimeError("getaddrinfo failed")
    try:
        bedrock_converse("x", model_id=HAIKU, bearer="tok", transport=boom)
        assert False, "transport error must raise"
    except BedrockError as e:
        assert "getaddrinfo" in str(e) or "failed" in str(e), str(e)
    print("PASS test_transport_error_raises_named")


def test_bad_response_shape_raises_named():
    def wrong(url, headers, body, timeout):
        return json.dumps({"not": "converse"})
    try:
        bedrock_converse("x", model_id=HAIKU, bearer="tok", transport=wrong)
        assert False, "bad shape must raise"
    except BedrockError as e:
        assert "shape" in str(e).lower(), str(e)
    print("PASS test_bad_response_shape_raises_named")


def test_make_judge_over_converse_scores_and_abstains():
    good = converse_invoke(
        model_id=HAIKU, bearer="tok",
        transport=lambda u, h, b, t: json.dumps({"output": {"message": {"content": [{"text": '{"score": 0.8}'}]}}}))
    assert make_judge(good)("predicted", "actual") == 0.8
    # a Bedrock failure (raised) must make the judge ABSTAIN (None), never fabricate a grade.
    def boom(u, h, b, t):
        raise RuntimeError("model down")
    bad = converse_invoke(model_id=HAIKU, bearer="tok", transport=boom)
    assert make_judge(bad)("p", "a") is None
    print("PASS test_make_judge_over_converse_scores_and_abstains")


if __name__ == "__main__":
    for _n, _f in sorted(globals().items()):
        if _n.startswith("test_") and callable(_f):
            _f()
    print("ALL BEDROCK TESTS PASS")
