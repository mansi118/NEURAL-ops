"""SeatSupervisor — lifecycle for per-seat jcode processes (plan §3.4 / task T3).

BOX-GATED: spawns jailed jcode (server mode) via IsolationUnit. Crash → restart with backoff;
resumes the seat's session if jcode supports it. Implement after T2.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

SeatId = Tuple[str, str]


class SeatState(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    CRASHED = "crashed"
    STOPPED = "stopped"


@dataclass
class SeatStatus:
    seat: SeatId
    state: SeatState
    restarts: int = 0


@dataclass
class RunResult:
    seat: SeatId
    ok: bool
    transcript_ref: str | None = None


class SeatSupervisor:
    def start(self, seat: SeatId, cls) -> "object":
        raise NotImplementedError("T3 — box-gated")

    def stop(self, seat: SeatId) -> None:
        raise NotImplementedError("T3 — box-gated")

    def status(self, seat: SeatId) -> SeatStatus:
        raise NotImplementedError("T3 — box-gated")

    def run_once(self, seat: SeatId, prompt: str) -> RunResult:
        raise NotImplementedError("T3 — wraps `jcode run` (box-gated)")
