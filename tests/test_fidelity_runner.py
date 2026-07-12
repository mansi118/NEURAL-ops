"""Shadow-mode fidelity runner tests — the driver over injected seams, the pluggable score sink, and
the live-seam inertness. Offline, in-memory seams only, no network, nothing faked.
Run: python3 tests/test_fidelity_runner.py
"""
import json, os, pathlib, sys
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.fidelity_harness import FidelityLoop  # noqa: E402
from runtime.shadow import signals_from_events  # noqa: E402
from runtime import curator  # noqa: E402
from runtime.fidelity_runner import (run_shadow_pass, LocalFileScoreSink, ClickHouseScoreSink,  # noqa: E402
                                     PalaceFidelitySeams, ScoreSink)


def _shadow(pred, actual, cls="selective"):
    return {"kind": "shadow_prediction", "predicted": pred, "actual": actual, "class": cls}


# 70 lexical-agree + 30 disjoint-disagree finished-run events (free text, none exact matches)
def _traffic():
    agree = _shadow("please deploy the release now", "deploy the release right now please")
    disagree = _shadow("approve the refund", "penguins waddle across ice")
    return [dict(agree) for _ in range(70)] + [dict(disagree) for _ in range(30)]


class RecordingSeams:
    """In-memory FidelityLoop seams that LOG every call — so a test can assert the driver's only I/O
    is load_twin/load_events/save_twin (+ the sink). There is deliberately no block/mutate method."""

    def __init__(self, twins, events):
        self._twins = dict(twins)
        self._events = dict(events)
        self.calls = []

    def load_twin(self, tenant, seat):
        self.calls.append(("load_twin", tenant, seat))
        return self._twins.get((tenant, seat))

    def load_events(self, tenant, seat):
        self.calls.append(("load_events", tenant, seat))
        return list(self._events.get((tenant, seat), []))

    def save_twin(self, tenant, seat, twin):
        self.calls.append(("save_twin", tenant, seat))
        self._twins[(tenant, seat)] = twin


class ListSink(ScoreSink):
    def __init__(self):
        self.rows = []

    def write(self, tenant, seat, record):
        self.rows.append((tenant, seat, record))


def test_driver_records_curator_fidelity_per_seat():
    seams = RecordingSeams(
        twins={("neuraledge", "aria"): {"maturity": "growing", "version": 1}},
        events={("neuraledge", "aria"): _traffic(), ("neuraledge", "recon"): _traffic()})
    loop = FidelityLoop(seams.load_twin, seams.save_twin, seams.load_events)
    sink = ListSink()
    recs = run_shadow_pass(loop, "neuraledge", ["aria", "recon"], sink, sustained_days=30)

    assert [s for _, s, _ in sink.rows] == ["aria", "recon"], sink.rows      # one record per seat, in order
    expected = curator.fidelity(signals_from_events(_traffic()))             # 0.7
    for _, _, rec in sink.rows:
        assert rec["fidelity"] == expected == 0.7, rec
        assert rec["breakdown"]["blended"] == expected, rec                  # honest breakdown carried through
        assert rec["scored"] == 100, rec
    assert len(recs) == 2
    print("PASS test_driver_records_curator_fidelity_per_seat")


def test_empty_events_records_none_and_persists_nothing():
    seams = RecordingSeams(twins={}, events={("t", "s"): []})               # seed twin, no traffic
    loop = FidelityLoop(seams.load_twin, seams.save_twin, seams.load_events)
    sink = ListSink()
    run_shadow_pass(loop, "t", ["s"], sink)

    _, _, rec = sink.rows[0]
    assert rec["fidelity"] is None and rec["scored"] == 0, rec              # unscored, no crash
    assert rec["persisted"] is False, rec
    assert ("save_twin", "t", "s") not in seams.calls                        # a no-op pass writes no twin
    print("PASS test_empty_events_records_none_and_persists_nothing")


def test_shadow_mode_only_io_is_the_injected_seams():
    seams = RecordingSeams(
        twins={("t", "a"): {"maturity": "growing", "version": 1}},
        events={("t", "a"): _traffic()})
    loop = FidelityLoop(seams.load_twin, seams.save_twin, seams.load_events)
    sink = ListSink()
    run_shadow_pass(loop, "t", ["a"], sink, sustained_days=30)

    kinds = [c[0] for c in seams.calls]
    # exactly the read/persist seam calls — no "block", "deny", "gate", or any other live mutation path
    assert kinds == ["load_twin", "load_events", "save_twin"], seams.calls
    assert set(kinds) <= {"load_twin", "load_events", "save_twin"}
    assert len(sink.rows) == 1                                              # the sink is the only other sink of I/O
    print("PASS test_shadow_mode_only_io_is_the_injected_seams")


def test_localfile_sink_writes_readable_jsonl(tmp_path=None):
    base = pathlib.Path(tmp_path) if tmp_path else R / "tests" / "_tmp_fidelity"
    base.mkdir(parents=True, exist_ok=True)
    out = base / "scores.jsonl"
    if out.exists():
        out.unlink()
    sink = LocalFileScoreSink(out, now=lambda: "2026-07-12T00:00:00+00:00")
    sink.write("neuraledge", "aria", {"fidelity": 0.7, "scored": 100})
    sink.write("neuraledge", "recon", {"fidelity": None, "scored": 0})

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rows = [json.loads(ln) for ln in lines]                                # valid JSONL, re-readable
    assert rows[0] == {"tenant": "neuraledge", "seat": "aria", "fidelity": 0.7,
                       "scored": 100, "at": "2026-07-12T00:00:00+00:00"}, rows[0]
    assert rows[1]["fidelity"] is None and rows[1]["at"] == "2026-07-12T00:00:00+00:00"
    out.unlink()
    print("PASS test_localfile_sink_writes_readable_jsonl")


def test_localfile_sink_no_wallclock_without_now():
    base = R / "tests" / "_tmp_fidelity"
    base.mkdir(parents=True, exist_ok=True)
    out = base / "scores_no_ts.jsonl"
    if out.exists():
        out.unlink()
    LocalFileScoreSink(out).write("t", "s", {"fidelity": 0.5})             # no `now` injected
    row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert "at" not in row, row                                            # timestamp is the sink's concern, opt-in
    out.unlink()
    print("PASS test_localfile_sink_no_wallclock_without_now")


def test_live_seams_are_inert_at_construction():
    # Construction touches nothing: no network, no import of memory internals, no env needed.
    seams = PalaceFidelitySeams("palaceX")
    assert seams.palace_id == "palaceX" and seams.EVENTS_TOOL == "palace_get_run_events"

    from runtime.memory import MemPalaceError
    saved = dict(os.environ)
    for k in ("CONVEX_DEPLOYMENT_URL", "CONVEX_SITE_URL"):
        os.environ.pop(k, None)
    try:
        # a valid seat → the credential gate fires (no network attempted), not a construction error
        for call in (lambda: seams.load_events("palaceX", "aria"),
                     lambda: seams.load_twin("palaceX", "aria"),
                     lambda: seams.save_twin("palaceX", "aria", {"version": 1, "maturity": "seed"})):
            try:
                call(); assert False, "must refuse without CONVEX_* creds"
            except MemPalaceError as e:
                assert "not set" in str(e), str(e)
        # a blank seat → L4 fail-closed (no implicit-identity/_admin row) before any network
        try:
            seams.load_events("palaceX", "  "); assert False
        except MemPalaceError as e:
            assert "denied_at_layer=broker" in str(e), str(e)
    finally:
        os.environ.clear(); os.environ.update(saved)
    print("PASS test_live_seams_are_inert_at_construction")


def test_clickhouse_sink_is_a_loud_seam():
    sink = ClickHouseScoreSink("dsn://unused")                             # construction inert
    try:
        sink.write("t", "s", {"fidelity": 0.5}); assert False, "must not silently swallow"
    except NotImplementedError as e:
        assert "Track-2" in str(e) or "Track 2" in str(e), str(e)
    print("PASS test_clickhouse_sink_is_a_loud_seam")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL FIDELITY RUNNER TESTS PASS")
