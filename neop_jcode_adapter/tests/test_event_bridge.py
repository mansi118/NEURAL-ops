"""T4 tests for EventBridge — NEop lifecycle + significant events (local-log fallback)."""
import pytest

from neop_jcode_adapter.event_bridge import EventBridge, LIFECYCLE_STATES

FIXED = lambda: 1_750_000_000.0


def bridge(tmp_path, **kw):
    return EventBridge(str(tmp_path / "events.jsonl"), clock=FIXED, **kw)


def test_no_destination_raises():
    with pytest.raises(ValueError):
        EventBridge(log_path=None)


def test_publish_writes_log_with_subject_and_ts(tmp_path):
    b = bridge(tmp_path)
    rec = b.publish("neop.significant.something", {"detail": 42})
    assert rec["subject"] == "neop.significant.something" and rec["detail"] == 42
    assert rec["ts"] == 1_750_000_000.0
    assert list(b.records())[0]["subject"] == "neop.significant.something"


def test_lifecycle_states_and_subjects(tmp_path):
    b = bridge(tmp_path)
    for state in LIFECYCLE_STATES:
        rec = b.lifecycle(("pal", "aria"), state)
        assert rec["subject"] == f"neop.lifecycle.{state}"
        assert rec["palaceId"] == "pal" and rec["neopId"] == "aria" and rec["state"] == state
    assert len(list(b.records())) == len(LIFECYCLE_STATES)


def test_unknown_lifecycle_state_raises(tmp_path):
    b = bridge(tmp_path)
    with pytest.raises(ValueError):
        b.lifecycle(("pal", "aria"), "exploded")  # closed vocabulary → no typo'd subjects


def test_convenience_methods(tmp_path):
    b = bridge(tmp_path)
    b.started(("pal", "aria"))
    b.crashed(("pal", "aria"), restarts=2)
    b.stopped(("pal", "aria"))
    b.promoted(("pal", "aria"), items=5)
    subs = [r["subject"] for r in b.records()]
    assert subs == [
        "neop.lifecycle.started",
        "neop.lifecycle.crashed",
        "neop.lifecycle.stopped",
        "neop.lifecycle.promoted",
    ]
    crashed = [r for r in b.records() if r["state"] == "crashed"][0]
    assert crashed["restarts"] == 2


def test_sink_forwarding(tmp_path):
    got = []
    b = bridge(tmp_path, sink=lambda subject, rec: got.append((subject, rec)))
    b.started(("pal", "aria"))
    assert got and got[0][0] == "neop.lifecycle.started"
