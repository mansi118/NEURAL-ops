"""Fidelity ingestion — record_verdict turns a Decision-Queue approve/reject into an authoritative
human-verdict run-event for the judged seat. PURE over an injected `put` (the palace write); no network.
Run: python3 tests/test_fidelity_ingest.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.fidelity_ingest import record_verdict   # noqa: E402
from runtime.shadow import signal_from_human_event   # noqa: E402


def _capture():
    calls = []

    def put(tenant, seat, event, *, kind, ts):
        calls.append({"tenant": tenant, "seat": seat, "event": event, "kind": kind, "ts": ts})
        return {"status": "ok", "trimmed": 0}
    return calls, put


def test_record_verdict_persists_human_verdict_for_the_seat():
    calls, put = _capture()
    res = record_verdict("neuraledge", "aria", "approve", proposal_id="p1", ts=123, put=put)
    assert res == {"status": "ok", "trimmed": 0}
    assert len(calls) == 1
    c = calls[0]
    assert c["tenant"] == "neuraledge" and c["seat"] == "aria" and c["kind"] == "human_verdict" and c["ts"] == 123
    assert c["event"]["agreed"] is True and c["event"]["proposal_id"] == "p1"
    # round-trips into an authoritative human signal (what the runner will fold)
    assert signal_from_human_event(c["event"])["method"] == "human"
    print("PASS test_record_verdict_persists_human_verdict_for_the_seat")


def test_reject_is_disagreement():
    calls, put = _capture()
    record_verdict("neuraledge", "recon", "reject", put=put)
    assert calls[0]["event"]["agreed"] is False
    print("PASS test_reject_is_disagreement")


def test_seat_is_explicit_never_guessed():
    # the seat must be passed — a verdict is about a specific NEop's output; the module does not infer it.
    calls, put = _capture()
    record_verdict("t", "seatX", "approve", put=put)
    assert calls[0]["seat"] == "seatX"
    print("PASS test_seat_is_explicit_never_guessed")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL FIDELITY INGEST TESTS PASS")
