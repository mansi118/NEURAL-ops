"""Live intent classifier (integration-mode) — a Haiku-class model -> (neop, confidence).

Lazy + credential-gated on ANTHROPIC_API_KEY; nothing here runs in unit mode (the
orchestrator uses recorded_classifier there). This is the live counterpart, used by
the recorded-vs-live agreement smoke to prove the mock/live boundary holds before any
COC routing ships. Mirrors runtime/aws.py and runtime/memory.py: name-is-contract,
mode decides recorded vs live.
"""
from __future__ import annotations
import os, json, pathlib

__all__ = ["ClassifierError", "live_classifier", "bedrock_classifier", "gemini_classifier",
           "openrouter_classifier", "catalog_from_agents", "BEDROCK_HAIKU", "GEMINI_MODEL",
           "OPENROUTER_MODEL"]

GEMINI_MODEL = "gemini-2.5-flash"   # free-tier model that actually has quota (2.0-flash = limit 0)

# OpenRouter routes to a Claude-class model WITHOUT the account-wide Bedrock block (see below).
# This is the production-parity classifier path: COC is Claude-based, so proving the recorded-vs-live
# seam against a Haiku-class Claude here closes the open production-lock question that Gemini (a
# different model family) can only prove for the SEAM, not for the shipping model. Overridable via
# OPENROUTER_MODEL_ID (e.g. "anthropic/claude-haiku-4.5" once confirmed live on the gateway).
OPENROUTER_MODEL = "anthropic/claude-3.5-haiku"

# BLOCKER (verified 2026-06-07, acct 071126865245 / user mansi-synlex):
# Bedrock model *invocation* is blocked account-wide. Converse/InvokeModel return
# 400 ValidationException "Operation not allowed" for EVERY vendor (Anthropic, Amazon
# Nova, Meta Llama) across ap-south-1 + us-east-1, direct id AND inference profile.
# It is NOT the Anthropic use-case form (that was the earlier guess): the block is
# vendor-independent. Diagnosis from the error shape:
#   - control-plane (ListFoundationModels / inference profiles) WORKS  -> creds valid
#   - 400 ValidationException, not 403 AccessDenied                    -> IAM allows InvokeModel;
#                                                                          the service itself refuses
#   => no model access is enabled at the ACCOUNT level. Fix = Bedrock console (account owner) ->
#      "Model access" -> request/enable the models (for Anthropic that includes the use-case form).
# Once cleared this default works; set BEDROCK_MODEL_ID to upgrade to 4.5 Haiku
# ("global.anthropic.claude-haiku-4-5-20251001-v1:0").
BEDROCK_HAIKU = "apac.anthropic.claude-3-haiku-20240307-v1:0"


def _classify_prompt(catalog, text):
    agents = "\n".join(f"- {k}: {v}" for k, v in catalog.items())
    return (
        "You route a user's chat message to exactly one agent. Agents:\n"
        f"{agents}\n\n"
        f"Message: {text!r}\n\n"
        'Respond with ONLY a JSON object: {"neop": "<agent_id>", "confidence": <0..1>}'
    )


def _parse(raw):
    try:
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        return str(data["neop"]), float(data["confidence"])
    except (ValueError, KeyError) as e:
        raise ClassifierError(f"unparseable classifier response: {raw!r}") from e


def _gemini_payload(catalog, text):
    """PURE: Gemini generateContent body. responseMimeType nudges clean JSON; thinkingBudget=0
    disables 2.5-flash's reasoning pass (else it spends the token budget thinking and returns
    empty) — routing needs the answer, not a chain of thought."""
    return {"contents": [{"parts": [{"text": _classify_prompt(catalog, text)}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 256,
                                 "responseMimeType": "application/json",
                                 "thinkingConfig": {"thinkingBudget": 0}}}


def _gemini_extract(resp):
    """PURE: pull the model's text out of a Gemini response (raises if absent)."""
    cands = resp.get("candidates") or []
    if not cands:
        raise ClassifierError(f"gemini: no candidates in response {resp!r}")
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    if not text:
        raise ClassifierError(f"gemini: empty content in response {resp!r}")
    return text


def gemini_classifier(catalog, model_id=None):
    """fn(text) -> (neop, confidence) via Google Gemini (REST, no SDK). Gated on GEMINI_API_KEY
    (or GOOGLE_API_KEY). Key rides the x-goog-api-key header — never the URL/query."""
    model_id = model_id or os.environ.get("GEMINI_MODEL_ID", GEMINI_MODEL)

    def fn(text):
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ClassifierError("GEMINI_API_KEY not set — required for the Gemini classifier")
        import urllib.request, urllib.error, time  # lazy
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
        req = urllib.request.Request(
            url, data=json.dumps(_gemini_payload(catalog, text)).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": key})
        for attempt in range(4):                            # transient 429/503 -> backoff 1,2,4s
            try:
                with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
                    return _parse(_gemini_extract(json.loads(r.read().decode())))
            except urllib.error.HTTPError as e:
                if e.code in (429, 503) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise
    return fn


def _openrouter_payload(catalog, text, model_id):
    """PURE: OpenRouter chat/completions body (OpenAI-compatible). No response_format — that's
    model-specific on the gateway and would error on backends that don't honor it; _parse already
    tolerates surrounding prose, so we lean on that instead. temperature=0 for determinism."""
    return {"model": model_id,
            "messages": [{"role": "user", "content": _classify_prompt(catalog, text)}],
            "max_tokens": 256, "temperature": 0}


def _openrouter_extract(resp):
    """PURE: pull the model's text out of an OpenRouter (OpenAI-shaped) response (raises if absent)."""
    choices = resp.get("choices") or []
    if not choices:
        raise ClassifierError(f"openrouter: no choices in response {resp!r}")
    text = (choices[0].get("message") or {}).get("content") or ""
    if not text:
        raise ClassifierError(f"openrouter: empty content in response {resp!r}")
    return text


def openrouter_classifier(catalog, model_id=None):
    """fn(text) -> (neop, confidence) via OpenRouter (REST, no SDK). Gated on OPENROUTER_API_KEY.
    Key rides the Authorization: Bearer header — never the URL/query. Routes to a Claude-class model
    by default, sidestepping the account-wide Bedrock block."""
    model_id = model_id or os.environ.get("OPENROUTER_MODEL_ID", OPENROUTER_MODEL)

    def fn(text):
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ClassifierError("OPENROUTER_API_KEY not set — required for the OpenRouter classifier")
        import urllib.request, urllib.error, time  # lazy
        url = "https://openrouter.ai/api/v1/chat/completions"
        req = urllib.request.Request(
            url, data=json.dumps(_openrouter_payload(catalog, text, model_id)).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        for attempt in range(4):                            # transient 429/502/503 -> backoff 1,2,4s
            try:
                with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
                    return _parse(_openrouter_extract(json.loads(r.read().decode())))
            except urllib.error.HTTPError as e:
                if e.code in (429, 502, 503) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise
    return fn


def bedrock_classifier(catalog, model_id=BEDROCK_HAIKU, region="ap-south-1"):
    """fn(text) -> (neop, confidence) via a Haiku-class model on AWS Bedrock (Converse API).
    Uses the standard AWS credential chain — no separate key. Lazy boto3."""
    def fn(text):
        import boto3  # lazy
        br = boto3.client("bedrock-runtime", region_name=region)
        resp = br.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": _classify_prompt(catalog, text)}]}],
            inferenceConfig={"maxTokens": 120, "temperature": 0},
        )
        return _parse(resp["output"]["message"]["content"][0]["text"])
    return fn


class ClassifierError(RuntimeError):
    pass


def catalog_from_agents(agents_dir="agents", only=None):
    """Build {neop_id: one-line description} from agents/<id>/neop.md bodies.

    `only` optionally restricts to chat-routable destinations.
    """
    catalog = {}
    for neop_md in sorted(pathlib.Path(agents_dir).glob("*/neop.md")):
        text = neop_md.read_text()
        nid = neop_md.parent.name
        if only and nid not in only:
            continue
        # first non-empty prose line after the frontmatter/heading
        body = text.split("---", 2)[-1]
        desc = ""
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                desc = s
                break
        catalog[nid] = desc or nid
    return catalog


def live_classifier(catalog, model_id="claude-haiku-4-5"):
    """Return fn(text) -> (neop, confidence) backed by a live Haiku-class model."""
    def fn(text):
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ClassifierError("ANTHROPIC_API_KEY not set — required for the live classifier")
        import anthropic  # lazy
        client = anthropic.Anthropic(api_key=key)
        agents = "\n".join(f"- {k}: {v}" for k, v in catalog.items())
        prompt = (
            "You route a user's chat message to exactly one agent. Agents:\n"
            f"{agents}\n\n"
            f"Message: {text!r}\n\n"
            'Respond with ONLY a JSON object: {"neop": "<agent_id>", "confidence": <0..1>}'
        )
        msg = client.messages.create(
            model=model_id, max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        try:
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            return str(data["neop"]), float(data["confidence"])
        except (ValueError, KeyError) as e:
            raise ClassifierError(f"unparseable classifier response: {raw!r}") from e
    return fn
