"""IsolationUnit — one container per (palaceId, neopId); the tenant boundary while ACL is fail-open.

Plan §3.3 / task T2. BOX-GATED: needs Docker (plain on EC2, or inside Colima on the Mac mini) — not
runnable in the WSL dev box. Implement against the real container runtime once T0 is green.

Per seat: isolated JCODE_HOME, jailed working dir, NO host filesystem access, and egress restricted
to the palace endpoint + api.anthropic.com ONLY. The container boundary carries isolation because
the 4-layer ACL is fail-open until S0.3 (see CLAUDE.md invariant #3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

SeatId = Tuple[str, str]  # (palaceId, neopId)


@dataclass
class Handle:
    seat: SeatId
    container_id: str


class IsolationUnit:
    def launch(self, seat: SeatId, image: str, env: dict, workdir_mount: str) -> Handle:
        raise NotImplementedError("T2 — box-gated (Docker/Colima)")

    def egress_allowlist(self) -> list[str]:
        """Only the palace host + the Anthropic API. Everything else is dropped at the jail."""
        raise NotImplementedError("T2 — derive {palace host, api.anthropic.com} per seat")

    def teardown(self, handle: Handle) -> None:
        raise NotImplementedError("T2 — box-gated")
