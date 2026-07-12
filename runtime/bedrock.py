"""Bedrock Converse invoke (stdlib urllib) — a model-agnostic `invoke(prompt) -> str` for the Python
runtime, defaulting to **Claude Haiku**. The Converse API is uniform across Nova/Claude, so this is the
one place the Python runtime speaks to `bedrock-runtime`; callers inject the returned `invoke` (e.g.
`runtime.judge.make_judge(converse_invoke())` for the shadow-fidelity LLM-as-judge).

Claude on Bedrock is unblocked + verified (the bearer token invokes the Claude inference profiles in
ap-south-1). We default the JUDGE to **Haiku** — a cheap classification judgment, the fast tier of the
Haiku+Sonnet standard — NOT Nova. Auth is the bearer token pi-ai/the wrapper already use
(`AWS_BEARER_TOKEN_BEDROCK`), read at CALL time; region pinned to the spine (a us-east-1 token 403s in
ap-south-1). The HTTP transport is injectable (`transport=`) so the builder + parser are unit-tested
offline with no network. Every failure raises a NAMED `BedrockError` (so `make_judge` abstains → the
turn is left UNSCORED, never a fabricated grade). No wall-clock here.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# The cheap JUDGE tier — Claude Haiku on Bedrock (the global.* inference profile the on-demand Converse
# invoke needs; bare ids reject). Overridable via FIDELITY_JUDGE_MODEL. Deliberately NOT Nova.
DEFAULT_JUDGE_MODEL = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
_DEFAULT_REGION = "ap-south-1"


class BedrockError(RuntimeError):
    """A named Bedrock invoke failure (auth/region, egress, model, or bad shape). Callers that must not
    fail on a bad grade (the judge) catch this and abstain."""


def _urllib_transport(url, headers, body, timeout):
    """Default transport: POST via stdlib urllib, return the response body text. Injectable so the
    request BUILDER + response PARSER are testable without a network (pass `transport=`)."""
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def bedrock_converse(prompt, *, model_id, region=None, bearer=None, system=None,
                     max_tokens=512, temperature=0.0, timeout=30, transport=None) -> str:
    """One Converse turn → the assistant's text. `model_id` is the inference-profile id (e.g. the
    Claude Haiku default). region/bearer default from env at CALL time; blank bearer is fail-closed.
    Raises `BedrockError` (named) on any auth/egress/shape failure — never returns a partial guess."""
    region = region or os.environ.get("NRT_BEDROCK_REGION") or os.environ.get("AWS_REGION") or _DEFAULT_REGION
    bearer = bearer if bearer is not None else os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
    if not (bearer or "").strip():
        raise BedrockError("AWS_BEARER_TOKEN_BEDROCK is blank — fail-closed (no token, no invoke).")
    url = "https://bedrock-runtime.%s.amazonaws.com/model/%s/converse" % (region, model_id)
    body_obj = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system:
        body_obj["system"] = [{"text": system}]
    body = json.dumps(body_obj).encode("utf-8")
    headers = {"Authorization": "Bearer %s" % bearer, "Content-Type": "application/json"}
    t = transport or _urllib_transport
    try:
        raw = t(url, headers, body, timeout)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300] if hasattr(e, "read") else str(e)
        raise BedrockError("bedrock converse HTTP %s: %s" % (getattr(e, "code", "?"), detail))
    except BedrockError:
        raise
    except Exception as e:                                   # URLError (DNS/egress), timeout, transport bug
        raise BedrockError("bedrock converse call failed: %s" % e)
    try:
        data = json.loads(raw)
        parts = data["output"]["message"]["content"]         # Converse envelope (uniform Nova/Claude)
        return "".join(p.get("text", "") for p in parts).strip()
    except Exception:
        raise BedrockError("bedrock converse: unexpected response shape: %s" % (str(raw)[:200]))


def converse_invoke(*, model_id=None, **kw):
    """Return an `invoke(prompt) -> str` bound to a Bedrock Converse model — the shape
    `runtime.judge.make_judge` wraps. Defaults to Claude Haiku (`FIDELITY_JUDGE_MODEL` overrides). All
    other kwargs (region/bearer/system/max_tokens/temperature/timeout/transport) pass through to
    `bedrock_converse`, so tests inject `transport=` and no network is touched until `invoke` is called."""
    mid = model_id or os.environ.get("FIDELITY_JUDGE_MODEL") or DEFAULT_JUDGE_MODEL

    def _invoke(prompt):
        return bedrock_converse(prompt, model_id=mid, **kw)

    return _invoke
