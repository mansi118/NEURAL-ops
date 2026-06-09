"""Gated live smoke — recorded classifier fixtures vs a live Haiku-class model on AWS Bedrock.

verify-before-trust on the mock/live boundary: do our recorded classifier fixtures
agree with a real model? If recorded != live, COC routing is wrong the moment
NeuralChat ships — better to know now, before ACP is built on top.

SAFETY: read-only, no prod data, no writes. SKIPS cleanly (exit 0) when Bedrock is
unreachable (no AWS creds / model access), so it's safe in CI and as a committed artifact.
Uses the standard AWS credential chain (no separate key). Override the model with
BEDROCK_MODEL_ID. Run: python3 tests/smoke_classifier.py
"""
import os, sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from frontdoor.classifier import (  # noqa: E402
    bedrock_classifier, live_classifier, gemini_classifier, openrouter_classifier,
    catalog_from_agents, BEDROCK_HAIKU, GEMINI_MODEL, OPENROUTER_MODEL)

# Chat-routable destinations (ping/aws-probe/decision-shadow are not user-facing routes).
ROUTABLE = {"recon", "cortex", "echo", "interviewer"}

# (message, expected neop) — mirror what the recorded fixtures encode.
CASES = [
    ("find me leads in fintech startups", "recon"),
    ("what do you remember about our embedding model", "cortex"),
    ("hey, just saying hello", "echo"),
    ("I'm new here — set me up", "interviewer"),
]
CONF_GATE = 0.7


def main():
    catalog = catalog_from_agents(str(R / "agents"), only=ROUTABLE)
    # Provider selection. CLASSIFIER_PROVIDER forces one (gemini|openrouter|anthropic|bedrock) — use
    # `openrouter` to grade the recorded fixtures against a Claude-class model (production parity for
    # the COC production-lock decision). Otherwise auto-precedence: OpenRouter (Claude parity, no
    # Bedrock block) -> Gemini (free tier, seam-proven) -> Anthropic API -> Bedrock.
    forced = os.environ.get("CLASSIFIER_PROVIDER", "").strip().lower()
    has_or = bool(os.environ.get("OPENROUTER_API_KEY"))
    has_gem = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    has_ant = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if forced == "openrouter" or (not forced and has_or):
        model = os.environ.get("OPENROUTER_MODEL_ID", OPENROUTER_MODEL)
        clf, src = openrouter_classifier(catalog, model_id=model), f"OpenRouter {model}"
    elif forced == "gemini" or (not forced and has_gem):
        model = os.environ.get("GEMINI_MODEL_ID", GEMINI_MODEL)
        clf, src = gemini_classifier(catalog, model_id=model), f"Gemini {model}"
    elif forced == "anthropic" or (not forced and has_ant):
        clf, src = live_classifier(catalog), "Anthropic API (claude-haiku)"
    else:
        model = os.environ.get("BEDROCK_MODEL_ID", BEDROCK_HAIKU)
        clf, src = bedrock_classifier(catalog, model_id=model), f"Bedrock {model}"
    try:
        clf("ping")                          # reachability probe
    except Exception as e:                   # noqa: BLE001 — any creds/access failure -> skip
        print(f"SKIP: classifier unreachable via {src} ({type(e).__name__}: {str(e)[:70]}) — deferred.")
        return 0
    print(f"catalog ({len(catalog)} routable): {sorted(catalog)}")
    print(f"source: {src}\n")
    disagreements = []
    for text, expected in CASES:
        neop, conf = clf(text)
        agree = (neop == expected)
        gate = ">=gate" if conf >= CONF_GATE else "<gate"
        print(f"  {'OK  ' if agree else 'MISS'} {text!r} -> live={neop}({conf:.2f},{gate}) expected={expected}")
        if not agree:
            disagreements.append((text, expected, neop))
    if disagreements:
        print(f"\nDISAGREEMENT: {len(disagreements)}/{len(CASES)} — recorded fixtures != live; COC routing at risk.")
        return 1
    print(f"\nAGREEMENT: recorded fixtures match the live classifier on {len(CASES)}/{len(CASES)} cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
