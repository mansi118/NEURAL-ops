"""Shadow-mode fidelity scorer (Flow 5 companion) — grade a NEop's shadow prediction against
the human's actual reply into a Decision-Shadow *signal* that the Curator consumes.

`core.py` owns the shadow EMISSION (`shadow_prediction {predicted, actual, agreed, class}`), but
its `agreed` is exact equality (`predicted == actual`) — which is ~always False on free-text NEop
replies, so a live fidelity clock fed by it reads ~0. This module is the grader that turns a
(predicted, actual) pair into a GRADED agreement, so the fidelity clock (`runtime/curator.py`) can
run on REAL Matrix traffic from day one — the plan's early-clock unlock — without a human label on
every turn. core.py is untouched; this is a leaf module that reads its shadow output and emits the
`{field, kind, agreed, ...}` shape `curator.fidelity`/`curate` already accept.

Layered, cheapest-first — the first CONFIDENT layer wins, so most turns cost nothing:
  1. exact    — normalized string equality (deterministic, free).
  2. lexical  — token Jaccard over normalized tokens: agree >= LEXICAL_AGREE, disagree <= LEXICAL_
                DISAGREE (deterministic, free). The ambiguous middle falls through.
  3. judge    — an INJECTED callable `judge(predicted, actual) -> float in [0,1]` (LLM-as-judge;
                Nova in-VPC live, a stub offline). Consulted ONLY on the ambiguous middle. With no
                judge, an ambiguous pair scores `agreed=None` — deliberately UNSCORED, so it never
                guesses and never pollutes the fidelity rate (curator ignores `agreed is None`).

Every signal carries PROVENANCE (`method` ∈ exact|lexical|judge|human, `authoritative` for human
labels) so the day-90 metric is reportable honestly: `fidelity_breakdown` splits blended vs
human-only vs machine-only. Pure + deterministic given the injected judge; no wall-clock, no I/O.
"""
from __future__ import annotations

import re

# Jaccard thresholds. Wide UNSCORED band between them on purpose — the judge (or a human) resolves
# the middle; without one we abstain rather than guess.
LEXICAL_AGREE = 0.6
LEXICAL_DISAGREE = 0.1
JUDGE_AGREE = 0.5

_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")


def _normalize(s) -> str:
    """Lowercase, strip punctuation, collapse whitespace. Non-strings are str()'d first (core.py's
    `predicted` is `next(iter(outputs.values()))` — any type)."""
    if s is None:
        return ""
    s = _PUNCT.sub(" ", str(s).lower())
    return _WS.sub(" ", s).strip()


def _tokens(s) -> set:
    n = _normalize(s)
    return set(n.split()) if n else set()


def jaccard(a: set, b: set) -> float:
    """|a ∩ b| / |a ∪ b|. Two empties agree (1.0); one-empty disagrees (0.0)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def grade(predicted, actual, *, judge=None):
    """Score one (predicted, actual) pair. → (agreed: bool|None, agreement: float|None, method).

    `agreed is None` means UNSCORED (a missing side, or an ambiguous pair with no judge) — the
    caller leaves it out of the fidelity rate rather than guessing.
    """
    if predicted is None or actual is None:
        return None, None, "unscored"
    if _normalize(predicted) == _normalize(actual):
        return True, 1.0, "exact"
    j = jaccard(_tokens(predicted), _tokens(actual))
    if j >= LEXICAL_AGREE:
        return True, round(j, 3), "lexical"
    if j <= LEXICAL_DISAGREE:
        return False, round(j, 3), "lexical"
    if judge is not None:
        s = max(0.0, min(1.0, float(judge(predicted, actual))))
        return (s >= JUDGE_AGREE), round(s, 3), "judge"
    return None, round(j, 3), "lexical_inconclusive"


def shadow_signal(predicted, actual, *, judge=None, field="decision_style",
                  kind="structural", decision_class="selective"):
    """Grade a shadow prediction into a Curator signal. Mirrors core.py's shadow_prediction shape
    (predicted/actual/agreed/class) and adds field/kind (for corroboration) + provenance."""
    agreed, agreement, method = grade(predicted, actual, judge=judge)
    return {
        "field": field, "kind": kind, "class": decision_class,
        "predicted": predicted, "actual": actual,
        "agreed": agreed, "agreement": agreement,
        "method": method, "authoritative": False,
    }


def human_signal(agreed, *, field="decision_style", kind="structural", decision_class="selective"):
    """An explicit human verdict (e.g. a Decision-Queue thumbs up/down). Authoritative — always
    scored, provenance `human`, and reported in the honest human-only fidelity."""
    a = bool(agreed)
    return {
        "field": field, "kind": kind, "class": decision_class,
        "predicted": None, "actual": None,
        "agreed": a, "agreement": 1.0 if a else 0.0,
        "method": "human", "authoritative": True,
    }


def _rate(xs):
    return round(sum(1 for s in xs if s["agreed"]) / len(xs), 3) if xs else None


def fidelity_breakdown(signals):
    """Honest fidelity report over a signal window. `blended` equals `curator.fidelity` for the same
    signals; `human_only` is the authoritative number; `machine_only` isolates lexical/judge labels.
    Splitting them keeps the day-90 metric from being inflated by synthetic (judge) agreement."""
    scored = [s for s in signals if s.get("agreed") is not None]
    human = [s for s in scored if s.get("method") == "human"]
    machine = [s for s in scored if s.get("method") != "human"]
    by_method = {}
    for s in scored:
        by_method[s.get("method")] = by_method.get(s.get("method"), 0) + 1
    return {
        "blended": _rate(scored),
        "human_only": _rate(human),
        "machine_only": _rate(machine),
        "n_scored": len(scored),
        "n_human": len(human),
        "n_machine": len(machine),
        "n_unscored": sum(1 for s in signals if s.get("agreed") is None),
        "by_method": by_method,
    }
