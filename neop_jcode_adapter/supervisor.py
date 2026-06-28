"""SeatSupervisor — lifecycle for per-seat jcode processes (plan §3.4 / task T3).

Crash → restart with backoff; resumes the seat's session. Spawns jailed jcode via IsolationUnit.

WHAT'S OFFLINE-BUILDABLE (here, tested): the pure lifecycle LOGIC — `build_run_argv` (the jcode CLI
argv), `seat_env` (per-seat JCODE_HOME + model-key passthrough by NAME, no secret embedded),
`backoff_delay` (restart backoff), and the in-memory state machine. WHAT'S BOX-GATED (T0, Docker +
a runnable jcode binary): `_spawn` / the actual subprocess — validated on a box at T0, not here.

jcode CLI (verified from jcode@master src/cli/args.rs):
  * one-shot:  ``jcode run "<prompt>"``  (``--json`` machine-readable, ``--stream`` NDJSON)
  * server:    ``jcode serve`` / ``jcode server stop`` / ``jcode connect``
  * resume:    top-level flag ``jcode --resume <SESSION_ID>`` (a "seat" maps to a session id)
  * isolation: distinct ``JCODE_HOME`` per seat; the model key (ANTHROPIC_API_KEY / OPENROUTER_API_KEY)
    arrives via the jailed container env — NEVER a CLI arg (no secret on a process arg line).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

SeatId = Tuple[str, str]

JCODE_BIN = "jcode"
RESTART_BASE_SECS = 2.0
RESTART_CAP_SECS = 60.0
MAX_RESTARTS = 5


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
    transcript_ref: Optional[str] = None


def session_id(seat: SeatId) -> str:
    """A seat maps to a stable jcode session id (so `--resume` continues the same seat)."""
    pid, nid = seat
    return f"{pid}__{nid}"


def build_run_argv(prompt: str, *, resume: bool = False, seat: Optional[SeatId] = None,
                   json: bool = True, stream: bool = False) -> List[str]:
    """The jcode CLI argv for one invocation. Pure — no exec. `--resume <session>` (top-level flag)
    continues a seat; otherwise a fresh `run`. The model key is NEVER an arg (it rides the env)."""
    if not (prompt and prompt.strip()):
        raise ValueError("build_run_argv: blank prompt — refusing")
    argv = [JCODE_BIN]
    if resume:
        if seat is None:
            raise ValueError("build_run_argv: resume=True requires seat (for the session id)")
        argv += ["--resume", session_id(seat)]
    argv += ["run", prompt]
    if json:
        argv.append("--json")
    if stream:
        argv.append("--stream")
    return argv


def seat_env(seat: SeatId, jcode_home: str, *, key_env_names: List[str], base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Per-seat environment: a distinct JCODE_HOME + the model-key env vars passed THROUGH by name
    (values come from the launcher's env — never synthesized here). Fail-closed on blank scope/home."""
    pid, nid = seat
    if not (pid and pid.strip()) or not (nid and nid.strip()):
        raise ValueError("seat_env: blank palaceId/neopId — refusing (fail-closed scope)")
    if not (jcode_home and jcode_home.strip()):
        raise ValueError("seat_env: blank jcode_home — refusing")
    src = base_env if base_env is not None else os.environ
    env = {"JCODE_HOME": jcode_home}
    for name in key_env_names:
        if "=" in name:
            raise ValueError(f"key_env_names must be NAMES only — got {name!r}")
        if name in src:
            env[name] = src[name]   # forward the value from the launcher env; not invented here
    return env


def backoff_delay(restarts: int, *, base: float = RESTART_BASE_SECS, cap: float = RESTART_CAP_SECS) -> float:
    """Exponential restart backoff, capped. restarts=0 → base; grows ×2; never exceeds cap."""
    if restarts < 0:
        raise ValueError("backoff_delay: restarts must be >= 0")
    return min(cap, base * (2 ** restarts))


class SeatSupervisor:
    """Tracks per-seat state in memory; the actual spawn (`_spawn`) is box-gated (Docker + jcode binary).
    The lifecycle transitions + argv/env construction are pure and offline-tested."""

    def __init__(self, *, max_restarts: int = MAX_RESTARTS):
        self._status: Dict[SeatId, SeatStatus] = {}
        self.max_restarts = max_restarts

    def status(self, seat: SeatId) -> SeatStatus:
        return self._status.get(seat, SeatStatus(seat=seat, state=SeatState.STOPPED))

    def _mark(self, seat: SeatId, state: SeatState, *, restarts: Optional[int] = None) -> SeatStatus:
        cur = self._status.get(seat, SeatStatus(seat=seat, state=SeatState.STOPPED))
        st = SeatStatus(seat=seat, state=state, restarts=restarts if restarts is not None else cur.restarts)
        self._status[seat] = st
        return st

    def note_crash(self, seat: SeatId) -> bool:
        """Record a crash; return True if a restart is still allowed (under max_restarts)."""
        cur = self.status(seat)
        self._mark(seat, SeatState.CRASHED, restarts=cur.restarts + 1)
        return (cur.restarts + 1) <= self.max_restarts

    def start(self, seat: SeatId, cls) -> SeatStatus:
        self._mark(seat, SeatState.STARTING)
        self._spawn(seat, cls)               # box-gated; raises on the dev box
        return self._mark(seat, SeatState.RUNNING)

    def stop(self, seat: SeatId) -> None:
        self._mark(seat, SeatState.STOPPED)
        self._spawn_stop(seat)               # box-gated

    def run_once(self, seat: SeatId, prompt: str) -> RunResult:
        build_run_argv(prompt, seat=seat)    # validate argv (pure) before the box-gated exec
        return self._spawn_run_once(seat, prompt)   # box-gated

    # ── box-gated boundary (T0: Docker + a runnable jcode binary) ─────────────
    def _spawn(self, seat: SeatId, cls):
        raise NotImplementedError("box-gated: launch jailed jcode via IsolationUnit (T0 box)")

    def _spawn_stop(self, seat: SeatId):
        raise NotImplementedError("box-gated: stop the seat's jcode process/container (T0 box)")

    def _spawn_run_once(self, seat: SeatId, prompt: str) -> RunResult:
        raise NotImplementedError("box-gated: `jcode run` inside the jail (T0 box)")
