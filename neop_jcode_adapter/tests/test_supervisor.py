"""Tests for the offline-buildable lifecycle core of SeatSupervisor (jcode argv/env/backoff/state).
The actual spawn (_spawn*) is box-gated (T0) and not exercised here."""
import pytest

from neop_jcode_adapter.supervisor import (
    SeatSupervisor, SeatState, build_run_argv, seat_env, backoff_delay, session_id)

SEAT = ("palace1", "aria")


# ── jcode argv (the model key is NEVER an arg) ────────────────────────────────
def test_build_run_argv_fresh():
    assert build_run_argv("hello") == ["jcode", "run", "hello", "--json"]


def test_build_run_argv_resume_uses_session():
    argv = build_run_argv("go on", resume=True, seat=SEAT)
    assert "--resume" in argv and session_id(SEAT) in argv and "run" in argv


def test_build_run_argv_blank_prompt_refused():
    with pytest.raises(ValueError):
        build_run_argv("   ")


def test_build_run_argv_resume_needs_seat():
    with pytest.raises(ValueError):
        build_run_argv("x", resume=True)


def test_no_secret_on_arg_line():
    argv = build_run_argv("summarize the doc", seat=SEAT)
    blob = " ".join(argv)
    assert "sk-or-" not in blob and "sk-ant" not in blob
    assert "API_KEY" not in blob   # the key rides the env, never the argv


# ── per-seat env: JCODE_HOME + key passthrough by name ────────────────────────
def test_seat_env_passes_key_by_value_from_base_env():
    env = seat_env(SEAT, "/seats/p1/aria", key_env_names=["OPENROUTER_API_KEY"],
                   base_env={"OPENROUTER_API_KEY": "sk-or-xyz", "IRRELEVANT": "1"})
    assert env["JCODE_HOME"] == "/seats/p1/aria"
    assert env["OPENROUTER_API_KEY"] == "sk-or-xyz"   # forwarded from the launcher env
    assert "IRRELEVANT" not in env                    # only the named keys are forwarded


def test_seat_env_skips_absent_key():
    env = seat_env(SEAT, "/h", key_env_names=["OPENROUTER_API_KEY"], base_env={})
    assert "OPENROUTER_API_KEY" not in env            # absent in launcher env ⇒ not synthesized


def test_seat_env_failclosed():
    with pytest.raises(ValueError):
        seat_env(("", "aria"), "/h", key_env_names=[], base_env={})
    with pytest.raises(ValueError):
        seat_env(SEAT, "  ", key_env_names=[], base_env={})
    with pytest.raises(ValueError):
        seat_env(SEAT, "/h", key_env_names=["NAME=val"], base_env={})


# ── restart backoff ───────────────────────────────────────────────────────────
def test_backoff_grows_and_caps():
    assert backoff_delay(0) == 2.0
    assert backoff_delay(1) == 4.0
    assert backoff_delay(2) == 8.0
    assert backoff_delay(100) == 60.0   # capped
    with pytest.raises(ValueError):
        backoff_delay(-1)


# ── state machine + box-gate boundary ─────────────────────────────────────────
def test_status_defaults_stopped():
    assert SeatSupervisor().status(SEAT).state == SeatState.STOPPED


def test_note_crash_increments_and_caps():
    s = SeatSupervisor(max_restarts=2)
    assert s.note_crash(SEAT) is True   # 1
    assert s.note_crash(SEAT) is True   # 2
    assert s.note_crash(SEAT) is False  # 3 > max
    assert s.status(SEAT).state == SeatState.CRASHED
    assert s.status(SEAT).restarts == 3


def test_start_marks_then_hits_box_gate():
    s = SeatSupervisor()
    with pytest.raises(NotImplementedError):   # _spawn is box-gated
        s.start(SEAT, cls="A")
    assert s.status(SEAT).state == SeatState.STARTING   # transitioned before the box exec


def test_run_once_validates_before_box_gate():
    with pytest.raises(ValueError):            # blank prompt fails validation, not the box gate
        SeatSupervisor().run_once(SEAT, "   ")
    with pytest.raises(NotImplementedError):   # valid prompt reaches the box-gated exec
        SeatSupervisor().run_once(SEAT, "do the thing")
