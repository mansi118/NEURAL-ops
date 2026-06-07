"""Phase B — twin live-client marshalling (offline-gradeable; live smoke deferred to creds).

A twin is ADDRESSED, not searched: one record per (tenant=palaceId, seat=neopId) in a dedicated
`twins` table, read/written by address via palace_get_twin / palace_put_twin (blind upsert,
latest wins — broker owns versioning). The network call (_post) is credential-gated; everything
testable offline is the PURE marshalling + the gate itself. Live round-trip runs in the joint
Convex session. Run: python3 tests/test_memory_twin.py
"""
import os, json, sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime import memory as m   # noqa: E402

TWIN = {"twin_id": "neuraledge:aria", "version": 3, "maturity": "growing",
        "identity": "NeuralEDGE founder", "communication": "direct", "decision_style": "data-first"}


def test_put_params_serializes_doc():
    p = m.twin_put_params(TWIN)
    assert p["version"] == 3 and p["maturity"] == "growing", p          # denormalized for server reads
    assert json.loads(p["doc"]) == TWIN, p                              # doc round-trips to exact twin
    assert p["doc"] == json.dumps(TWIN, sort_keys=True), p             # deterministic (sorted keys)
    print("PASS test_put_params_serializes_doc")


def test_parse_twin_from_response():
    assert m.twin_from_response({"twin": TWIN, "version": 3}) == TWIN   # {twin:<obj>} shape
    assert m.twin_from_response({"twin": None}) is None                 # not-found -> None
    assert m.twin_from_response({}) is None                             # absent -> None
    assert m.twin_from_response(None) is None                           # no response -> None, no crash
    print("PASS test_parse_twin_from_response")


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
