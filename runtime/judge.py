"""LLM-as-judge for shadow-mode fidelity — the pluggable grader `shadow.grade(judge=...)` consults on
the ambiguous middle. This module is PURE except for an injected `invoke(prompt) -> str` (the model
call): **Claude Haiku on Bedrock** in-VPC live (via `runtime.bedrock.converse_invoke`; the cheap fast
tier — NOT Nova), a stub offline. It builds the prompt, parses the score, and wraps both into the
`judge(predicted, actual) -> float | None` callable shadow.py expects.

Honesty over coverage: a parse failure or a model error returns None (abstain), and `shadow.grade`
turns that into an UNSCORED signal — the judge never fabricates agreement from a bad or empty grade.
No wall-clock, no network here; the network is entirely in the injected `invoke`.
"""
from __future__ import annotations

import json
import re

DEFAULT_RUBRIC = (
    "Rate how well the PROPOSED reply agrees with the ACTUAL reply in intent and decision — not "
    "wording. 1.0 = same decision/intent; 0.0 = opposite, unrelated, or a refusal vs an answer."
)

_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_SCORE_KEYS = ("score", "agreement", "rating", "value")


def judge_prompt(predicted, actual, *, rubric=None) -> str:
    """Deterministic grading prompt. Asks for a bare JSON score so the parse is robust and cheap."""
    return (
        "You are grading agreement between two chat replies.\n"
        f"{rubric or DEFAULT_RUBRIC}\n"
        'Return ONLY a JSON object: {"score": <number between 0 and 1>}. No prose, no explanation.\n\n'
        f"PROPOSED:\n{predicted}\n\nACTUAL:\n{actual}\n"
    )


def _clamp(x) -> float:
    return max(0.0, min(1.0, float(x)))


def parse_judge_score(text):
    """Model output → float in [0,1], or None if nothing parseable. Handles a JSON object with a
    score-like key, a bare number, and an explicit percent. Out-of-range numbers clamp (a model that
    overshoots to 1.5 means 'max agreement', not 1.5%)."""
    if text is None:
        return None
    t = str(text).strip()
    if not t:
        return None
    if t[0] in "{[":
        try:
            obj = json.loads(t)
        except (ValueError, TypeError):
            obj = None
        if isinstance(obj, dict):
            for k in _SCORE_KEYS:
                v = obj.get(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return _clamp(v)
    m = _NUM.search(t)
    if not m:
        return None
    val = float(m.group())
    if "%" in t:
        val /= 100.0
    return _clamp(val)


def make_judge(invoke, *, rubric=None):
    """Wrap an injected `invoke(prompt) -> str` model call into `judge(predicted, actual) -> float|None`.
    A model exception or an unparseable response returns None (abstain) — the caller leaves the turn
    unscored rather than guessing. Pass the result straight to `shadow.grade(judge=...)`."""
    def _judge(predicted, actual):
        try:
            raw = invoke(judge_prompt(predicted, actual, rubric=rubric))
        except Exception:
            return None
        return parse_judge_score(raw)
    return _judge
