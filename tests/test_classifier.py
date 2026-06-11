"""Classifier marshalling tests (offline-gradeable) — prompt build, response parse, Gemini
payload/extract, and the credential gate. The live verdict (does a real model agree with the
recorded fixtures?) is smoke_classifier.py; this proves the pure plumbing around it.
Run: python3 tests/test_classifier.py
"""
import os, sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from frontdoor import classifier as c   # noqa: E402

CATALOG = {"recon": "find leads", "cortex": "recall memory", "echo": "say hi"}


def test_prompt_lists_agents():
    p = c._classify_prompt(CATALOG, "find me fintech leads")
    assert "recon: find leads" in p and "cortex: recall memory" in p, p
    assert "find me fintech leads" in p and '"neop"' in p and '"confidence"' in p, p
    print("PASS test_prompt_lists_agents")


def test_parse_extracts_json():
    assert c._parse('{"neop": "recon", "confidence": 0.9}') == ("recon", 0.9)
    # tolerates surrounding prose / code fences
    assert c._parse('here you go:\n```json\n{"neop":"cortex","confidence":0.7}\n```') == ("cortex", 0.7)
    for bad in ("not json", "{}", '{"neop":"x"}'):
        try:
            c._parse(bad)
            assert False, f"expected ClassifierError on {bad!r}"
        except c.ClassifierError:
            pass
    print("PASS test_parse_extracts_json")


def test_gemini_payload():
    pay = c._gemini_payload(CATALOG, "hi there")
    assert pay["contents"][0]["parts"][0]["text"].endswith('{"neop": "<agent_id>", "confidence": <0..1>}')
    assert pay["generationConfig"]["temperature"] == 0, pay
    assert pay["generationConfig"]["responseMimeType"] == "application/json", pay
    print("PASS test_gemini_payload")


def test_gemini_extract_and_roundtrip():
    resp = {"candidates": [{"content": {"parts": [{"text": '{"neop":"recon","confidence":0.88}'}]}}]}
    assert c._gemini_extract(resp) == '{"neop":"recon","confidence":0.88}'
    assert c._parse(c._gemini_extract(resp)) == ("recon", 0.88)            # full marshalling round-trip
    for bad in ({"candidates": []}, {"candidates": [{"content": {"parts": []}}]}):
        try:
            c._gemini_extract(bad)
            assert False, f"expected ClassifierError on {bad!r}"
        except c.ClassifierError:
            pass
    print("PASS test_gemini_extract_and_roundtrip")


def test_openrouter_payload():
    pay = c._openrouter_payload(CATALOG, "hi there", "anthropic/claude-3.5-haiku")
    assert pay["model"] == "anthropic/claude-3.5-haiku", pay
    assert pay["messages"][0]["role"] == "user", pay
    assert pay["messages"][0]["content"].endswith('{"neop": "<agent_id>", "confidence": <0..1>}')
    assert pay["temperature"] == 0, pay
    print("PASS test_openrouter_payload")


def test_openrouter_extract_and_roundtrip():
    resp = {"choices": [{"message": {"role": "assistant", "content": '{"neop":"recon","confidence":0.91}'}}]}
    assert c._openrouter_extract(resp) == '{"neop":"recon","confidence":0.91}'
    assert c._parse(c._openrouter_extract(resp)) == ("recon", 0.91)        # full marshalling round-trip
    for bad in ({"choices": []}, {"choices": [{"message": {"content": ""}}]}, {"choices": [{"message": {}}]}):
        try:
            c._openrouter_extract(bad)
            assert False, f"expected ClassifierError on {bad!r}"
        except c.ClassifierError:
            pass
    print("PASS test_openrouter_extract_and_roundtrip")


def test_openrouter_credential_gated():
    saved = os.environ.pop("OPENROUTER_API_KEY", None)
    try:
        clf = c.openrouter_classifier(CATALOG)
        try:
            clf("hi")                                                       # no key -> refuse, never silent
            assert False, "expected ClassifierError without OPENROUTER_API_KEY"
        except c.ClassifierError as e:
            assert "OPENROUTER_API_KEY" in str(e), e
    finally:
        if saved is not None:
            os.environ["OPENROUTER_API_KEY"] = saved
    print("PASS test_openrouter_credential_gated")


def test_gemini_credential_gated():
    saved = {k: os.environ.pop(k, None) for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    try:
        clf = c.gemini_classifier(CATALOG)
        try:
            clf("hi")                                                       # no key -> refuse, never silent
            assert False, "expected ClassifierError without GEMINI_API_KEY"
        except c.ClassifierError as e:
            assert "GEMINI_API_KEY" in str(e), e
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    print("PASS test_gemini_credential_gated")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL CLASSIFIER TESTS PASS")
