"""SafetyPolicy — map seat classes to per-surface action tiers (plan §3.5).

This module is the PURE policy matrix. `config_render` (T2) translates the rendered tiers into
jcode's actual safety-system config format (schema confirmed from the jcode clone). Keeping the
matrix here makes the policy auditable and unit-testable independent of jcode's config dialect.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict


class Tier(str, Enum):
    AUTO_ALLOW = "auto_allow"
    ALWAYS_DENY = "always_deny"
    PERMISSION_REQUIRED = "permission_required"
    SANDBOX_ONLY = "sandbox_only"  # allowed, but only inside a throwaway sandbox


# Non-palace tool surfaces every seat must have an explicit tier for (no silent surfaces, §6).
SURFACES = ("palace", "shell_host", "browser", "self_dev", "swarm_spawn")

# (plan §3.5) — keyed by seat class letter. "A" = NeP self-improvement lab; "B"/"C" = workers/build.
#
# IMPORTANT (per review 2026-06-18): Class A's SANDBOX_ONLY/AUTO_ALLOW tiers (live bash + swarm) are
# only safe when the container jail is ENFORCED. That jail is box-gated (Docker, S0.1 on target), so
# `config_render.disabled_tools(..., jail_enforced=False)` renders Class A as a WORKER (deny bash+swarm)
# until the caller asserts the jail is live — the config and the sandbox it assumes go live together.
# B vs C do NOT diverge in this matrix (C == B); their only difference is permission-gated swarm, which
# has no native ask-tier, so it lives entirely in the T5 pre_tool hook (see config_render).
SAFETY_MATRIX: Dict[str, Dict[str, Tier]] = {
    "A": {
        "palace": Tier.AUTO_ALLOW,
        "shell_host": Tier.SANDBOX_ONLY,
        "browser": Tier.ALWAYS_DENY,
        "self_dev": Tier.SANDBOX_ONLY,        # self-modify allowed ONLY in a throwaway sandbox
        "swarm_spawn": Tier.AUTO_ALLOW,       # within the sandbox
    },
    "B": {
        "palace": Tier.AUTO_ALLOW,
        "shell_host": Tier.ALWAYS_DENY,
        "browser": Tier.PERMISSION_REQUIRED,  # denied unless a task explicitly needs it
        "self_dev": Tier.ALWAYS_DENY,
        "swarm_spawn": Tier.PERMISSION_REQUIRED,
    },
}
SAFETY_MATRIX["C"] = SAFETY_MATRIX["B"]  # Class C (build) shares the worker posture


def render_tiers(seat_class: str) -> Dict[str, Tier]:
    """Return the per-surface tier map for a seat class. Raises on an unknown class — every seat
    must resolve to an explicit, complete policy (fail-closed, no silent surfaces)."""
    cls = seat_class.upper()
    if cls not in SAFETY_MATRIX:
        raise ValueError(f"unknown seat class {seat_class!r}; known: {sorted(SAFETY_MATRIX)}")
    tiers = SAFETY_MATRIX[cls]
    missing = set(SURFACES) - set(tiers)
    if missing:  # guard against an incomplete matrix row
        raise ValueError(f"seat class {cls} missing tiers for {sorted(missing)}")
    return dict(tiers)
