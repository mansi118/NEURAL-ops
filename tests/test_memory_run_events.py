"""run_events client marshalling (offline-gradeable; live smoke deferred to creds).

The INTERIM shadow-prediction store for the fidelity clock (Track 3): own-seat rows in the palace
`run_events` table, read/written by address via palace_get_run_events / palace_put_run_event. The
network call (_post) is credential-gated; everything testable offline is the PURE marshalling + the
gate. Live round-trip runs in the joint Convex session. Run: python3 tests/test_memory_run_events.py
"""
import os, sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime import memory as m   # noqa: E402

EVENT = {"kind": "shadow_prediction", "predicted": "reach out Monday", "actual": "yes, Monday", "class": "selective"}


def test_run_event_params_marshals():
    p = m.run_event_params(EVENT)
    assert p == {"kind": "shadow_prediction", "event": EVENT}, p         # default kind, no optional keys
    p2 = m.run_event_params(EVENT, kind="twin_written", run_id="r1", ts=123)
    assert p2["kind"] == "twin_written" and p2["runId"] == "r1" and p2["ts"] == 123, p2
    assert "runId" not in m.run_event_params(EVENT), "runId omitted when None"   # optionals stay absent
    print("PASS test_run_event_params_marshals")


def test_events_from_response():
    assert m.events_from_response({"events": [EVENT], "count": 1}) == [EVENT]    # {events:[...]} shape
    assert m.events_from_response({"events": [], "count": 0}) == []              # empty seat
    assert m.events_from_response({}) == []                                      # absent -> []
    assert m.events_from_response(None) == []                                    # no response -> [], no crash
    print("PASS test_events_from_response")


def test_live_path_is_credential_gated():
    # the offline guarantee: with no Convex creds, the live run-event calls REFUSE (never silently no-op).
    saved = {k: os.environ.pop(k, None) for k in ("CONVEX_DEPLOYMENT_URL", "CONVEX_SITE_URL")}
    try:
        for call in (lambda: m.get_run_events("neuraledge", "aria"),
                     lambda: m.put_run_event("neuraledge", "aria", EVENT)):
            try:
                call()
                assert False, "expected MemPalaceError without creds"
            except m.MemPalaceError:
                pass
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    print("PASS test_live_path_is_credential_gated")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL RUN-EVENTS CLIENT TESTS PASS")
