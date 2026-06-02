"""Gated live smoke — recorded classifier fixtures vs a live Haiku-class model.

verify-before-trust on the mock/live boundary: do our recorded classifier fixtures
agree with a real model? If recorded != live, COC routing is wrong the moment
NeuralChat ships — better to know now, before ACP is built on top.

SAFETY: read-only, no prod data, no writes. SKIPS cleanly (exit 0) when
ANTHROPIC_API_KEY is unset, so it's safe in CI and as a committed artifact.

Run: python3 tests/smoke_classifier.py
"""
import os, sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from frontdoor.classifier import live_classifier, catalog_from_agents  # noqa: E402

# Chat-routable destinations (ping/aws-probe/decision-shadow are not user-facing routes).
ROUTABLE = {"recon", "cortex", "echo", "interviewer"}

# (message, expected neop) — these mirror what the recorded fixtures encode.
CASES = [
    ("find me leads in fintech startups", "recon"),
    ("what do you remember about our embedding model", "cortex"),
    ("hey, just saying hello", "echo"),
    ("I'm new here — set me up", "interviewer"),
]
CONF_GATE = 0.7


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("SKIP: ANTHROPIC_API_KEY not set — live classifier smoke deferred (gate held, recorded-only).")
        return 0
    catalog = catalog_from_agents(str(R / "agents"), only=ROUTABLE)
    print(f"catalog ({len(catalog)} routable): {sorted(catalog)}")
    clf = live_classifier(catalog)
    disagreements = []
    for text, expected in CASES:
        neop, conf = clf(text)
        agree = (neop == expected)
        gate = "≥gate" if conf >= CONF_GATE else "<gate"
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
