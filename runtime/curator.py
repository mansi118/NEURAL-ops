"""Twin Curator + fidelity clock (Flow 6) — evolve a seed twin via CORROBORATED signals.

A pure decision layer over the twin (committing uses get_twin/put_twin elsewhere);
core.py is untouched. It owns:
  - the lifecycle state machine: seed -> growing -> mature -> drifted (-> growing on re-tune)
  - the fidelity clock: agreement_rate_30d from Decision-Shadow signals; `mature` needs
    >= 0.65 sustained 30 days
  - corroboration gating (T-6): a structural edit needs >= 3 signals, an additive edit >= 1;
    otherwise NO-OP (conservative bias — buffer, do nothing)

Signals come from `decision-shadow` (`shadow_prediction {agreed, class, ...}`). The async
daily-cron / session-close cadence is a scheduling concern; this module is the logic it runs.
"""
from __future__ import annotations

FIDELITY_MATURE = 0.65
SUSTAIN_DAYS = 30
STRUCTURAL_MIN = 3
ADDITIVE_MIN = 1
DRIFT_OVERRIDES = 3
STATES = ("seed", "growing", "mature", "drifted")


def fidelity(signals):
    """agreement_rate_30d = agreed / scored over the trailing window."""
    scored = [s for s in signals if s.get("agreed") is not None]
    if not scored:
        return None
    return round(sum(1 for s in scored if s["agreed"]) / len(scored), 3)


def corroborated(edit, signals):
    """T-6: structural edits need >= STRUCTURAL_MIN signals on that field, additive >= ADDITIVE_MIN."""
    n = sum(1 for s in signals if s.get("field") == edit.get("field"))
    need = STRUCTURAL_MIN if edit.get("kind") == "structural" else ADDITIVE_MIN
    return n >= need, n, need


def next_maturity(twin, signals, *, sustained_days=0, overrides=0, retune_accepted=False):
    cur = twin.get("maturity", "seed")
    fid = fidelity(signals)
    if cur == "seed":
        structural = sum(1 for s in signals if s.get("kind", "structural") == "structural")
        return "growing" if structural >= STRUCTURAL_MIN else "seed"
    if cur == "growing":
        if fid is not None and fid >= FIDELITY_MATURE and sustained_days >= SUSTAIN_DAYS:
            return "mature"
        return "growing"
    if cur == "mature":
        return "drifted" if overrides >= DRIFT_OVERRIDES else "mature"
    if cur == "drifted":
        return "growing" if retune_accepted else "drifted"
    return cur


def curate(twin, signals, edits, *, sustained_days=0, overrides=0, retune_accepted=False):
    """One curation pass: apply corroborated edits + advance maturity. Pure + versioned-on-change."""
    new = dict(twin)
    committed, buffered = [], []
    for e in edits:
        ok, n, need = corroborated(e, signals)
        (committed if ok else buffered).append(
            {"field": e["field"], "kind": e.get("kind"), "signals": n, "need": need})
        if ok:
            new[e["field"]] = e["value"]
    mat = next_maturity(twin, signals, sustained_days=sustained_days,
                        overrides=overrides, retune_accepted=retune_accepted)
    transitioned = mat != twin.get("maturity", "seed")
    if committed or transitioned:
        new["version"] = twin.get("version", 0) + 1
    new["maturity"] = mat
    new["fidelity_score"] = fidelity(signals)
    new["signals"] = {**(twin.get("signals") or {}),
                      "agreement_rate_30d": new["fidelity_score"],
                      "shadow_predictions": len(signals)}
    return {"twin": new, "maturity": mat, "transitioned": transitioned,
            "committed": committed, "buffered": buffered, "fidelity": new["fidelity_score"]}
