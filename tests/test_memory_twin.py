"""Phase B — twin live-client marshalling (offline-gradeable; live smoke deferred to creds).

A twin is ADDRESSED, not searched: one record per (tenant, seat), read/written by a
deterministic closetId via palace_get_closet / palace_put_closet (write-by-id upsert). The
network call (_post) is credential-gated; everything testable offline is the PURE marshalling
+ the gate itself. The live read/write smoke runs in the joint Convex session.
Run: python3 tests/test_memory_twin.py
"""
import os, sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime import memory as m   # noqa: E402

TWIN = {"twin_id": "neuraledge:aria", "version": 3, "maturity": "growing",
        "identity": "NeuralEDGE founder", "communication": "direct", "decision_style": "data-first"}


def test_closet_id_deterministic():
    assert m.twin_closet_id("aria") == "twin::aria"
    assert m.twin_closet_id("aria") == m.twin_closet_id("aria")   # stable -> write-by-id upserts same row
    assert m.twin_closet_id("aria") != m.twin_closet_id("cortex")
    print("PASS test_closet_id_deterministic")


def test_parse_twin_from_closet():
    assert m.twin_from_closet({"twin": TWIN}) == TWIN                       # structured field
    assert m.twin_from_closet({"content": '{"version": 1}'}) == {"version": 1}  # JSON content mirror
    assert m.twin_from_closet(None) is None                                 # no closet
    assert m.twin_from_closet({}) is None                                   # empty closet
    assert m.twin_from_closet({"content": "not json"}) is None             # garbage -> None, not crash
    print("PASS test_parse_twin_from_closet")


def test_put_params_roundtrip():
    p = m.twin_put_params("aria", TWIN)
    assert p["closetId"] == "twin::aria" and p["category"] == "twin", p
    assert p["twin"] == TWIN, p
    # the JSON content mirror parses back to the exact twin (round-trip through twin_from_closet)
    assert m.twin_from_closet({"content": p["content"]}) == TWIN, p
    print("PASS test_put_params_roundtrip")


def test_live_path_is_credential_gated():
    # the offline guarantee: with no Convex creds, the live twin calls REFUSE (never silently no-op).
    saved = {k: os.environ.pop(k, None) for k in ("CONVEX_DEPLOYMENT_URL", "CONVEX_SITE_URL")}
    try:
        for call in (lambda: m.get_twin("neuraledge", "aria"),
                     lambda: m.put_twin("neuraledge", "aria", TWIN)):
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
    print("ALL TWIN-CLIENT TESTS PASS")
