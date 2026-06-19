"""Seat-class policy presets (plan §4 T9/T10, §3.5).

  Class A — NeP self-improvement lab: sandboxed self-dev loop, human-gated promotion.
  Class B — swarm batch worker (e.g. recon / ALTE enrichment): no host shell, no self-dev.
  Class C — build worker: same posture as B.

A preset bundles the safety tiers (from safety_policy) with the runtime knobs the supervisor +
config renderer need. Pure data — no jcode/Docker dependency, so it is unit-testable now.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict

from .safety_policy import Tier, render_tiers


class SeatClass(str, Enum):
    A = "A"  # NeP lab
    B = "B"  # swarm worker
    C = "C"  # build worker


@dataclass(frozen=True)
class SeatClassPreset:
    seat_class: SeatClass
    description: str
    sandbox_required: bool          # must run in a throwaway sandbox (Class A self-dev)
    # swarm_enabled is the T5 pre_tool hook's INPUT, not the current rendered policy: the safety matrix
    # has no native ask-tier, so config_render disables the `swarm` tool for BOTH B and C until the hook
    # is real. Pre-hook, B==C in config (B's swarm is BLOCKED); once the hook exists it allows B's
    # gated swarm (swarm_enabled=True) and denies C's (False). This flag is where B/C will diverge.
    swarm_enabled: bool
    tiers: Dict[str, Tier] = field(default_factory=dict)


def _preset(cls: SeatClass, description: str, *, sandbox_required: bool, swarm_enabled: bool) -> SeatClassPreset:
    return SeatClassPreset(
        seat_class=cls,
        description=description,
        sandbox_required=sandbox_required,
        swarm_enabled=swarm_enabled,
        tiers=render_tiers(cls.value),
    )


SEAT_CLASS_PRESETS: Dict[SeatClass, SeatClassPreset] = {
    SeatClass.A: _preset(
        SeatClass.A,
        "NeP self-improvement lab — sandboxed self-dev, human-gated promotion",
        sandbox_required=True,
        swarm_enabled=True,
    ),
    SeatClass.B: _preset(
        SeatClass.B,
        "Swarm batch worker (recon/ALTE enrichment) — no host shell, no self-dev",
        sandbox_required=False,
        swarm_enabled=True,
    ),
    SeatClass.C: _preset(
        SeatClass.C,
        "Build worker — worker posture, build-scoped",
        sandbox_required=False,
        swarm_enabled=False,
    ),
}


def preset_for(seat_class) -> SeatClassPreset:
    cls = seat_class if isinstance(seat_class, SeatClass) else SeatClass(str(seat_class).upper())
    return SEAT_CLASS_PRESETS[cls]
