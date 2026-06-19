"""SeatSupervisor — lifecycle for per-seat jcode processes (plan §3.4 / task T3).

BOX-GATED: spawns jailed jcode via IsolationUnit. Crash → restart with backoff; resumes the seat's
session. Implement after T2.

jcode CLI (verified from jcode@master src/cli/args.rs):
  * one-shot:  ``jcode run "<prompt>"``  (add ``--json`` for a machine-readable result, ``--stream`` for NDJSON)
  * server:    ``jcode serve``  (daemon)  /  ``jcode server stop``  /  ``jcode connect``
  * resume:    top-level flag ``jcode --resume <SESSION_ID>``  (a "seat" maps to a session id)
  * isolation: distinct ``JCODE_HOME`` per seat (config+state+memory dir); ``ANTHROPIC_API_KEY`` in env.
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
