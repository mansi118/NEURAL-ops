"""Twin v0 (seed) — schema, validator, prompt-assembly helper.

twin.md is a per-(tenant, seat) structured record (Convex is SoT, same backend as
memory). v0 is the 'seed' twin the Interviewer produces. The fidelity clock
(seed -> growing -> mature -> drifted) and the Twin Curator are P-LATER — this
module is seed-only: enough to create a v0, validate it, version it, and prepend it
to a Pi-agent prompt (S2 T-5). Nothing here computes fidelity.
"""
from __future__ import annotations

# Minimal seed schema. The full twin (signals history, relationships, …) is P-later;
# these are the fields a v0 must carry to be usable.
SEED_REQUIRED = ["twin_id", "version", "maturity", "identity", "communication", "decision_style"]
MATURITY_STATES = ("seed", "growing", "mature", "drifted")


def validate_twin(twin) -> list:
    """Return a diagnostics list (errors only). Seed-level structural check."""
    if not isinstance(twin, dict):
        return [{"severity": "error", "code": "twin_not_object", "msg": "twin must be an object"}]
    errs = []
    for k in SEED_REQUIRED:
        if k not in twin or twin[k] in (None, ""):
            errs.append({"severity": "error", "code": "twin_missing_field", "msg": f"twin missing '{k}'"})
    mat = twin.get("maturity")
    if mat is not None and mat not in MATURITY_STATES:
        errs.append({"severity": "error", "code": "twin_bad_maturity", "msg": f"maturity '{mat}' invalid"})
    return errs


def twin_preamble(twin) -> str:
    """Text prepended to a Pi-agent's prompt before the model call (S2 T-5)."""
    if not twin:
        return ""
    body = twin.get("body") or ""
    return f'<twin id="{twin.get("twin_id")}" maturity="{twin.get("maturity")}">\n{body}\n</twin>\n'
