"""Live intent classifier (integration-mode) — a Haiku-class model -> (neop, confidence).

Lazy + credential-gated on ANTHROPIC_API_KEY; nothing here runs in unit mode (the
orchestrator uses recorded_classifier there). This is the live counterpart, used by
the recorded-vs-live agreement smoke to prove the mock/live boundary holds before any
COC routing ships. Mirrors runtime/aws.py and runtime/memory.py: name-is-contract,
mode decides recorded vs live.
"""
from __future__ import annotations
import os, json, pathlib

__all__ = ["ClassifierError", "live_classifier", "bedrock_classifier", "catalog_from_agents"]

BEDROCK_HAIKU = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


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
