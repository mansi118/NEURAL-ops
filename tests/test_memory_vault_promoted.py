"""vault_promoted client seams — is_promoted/mark_promoted/clear_promoted (offline; gate + interpret).

Own-seat markers for VL-5 (runtime/vault.py). Network is credential-gated; testable offline is the
response interpretation (via a fake _post) + the gate. Run: python3 tests/test_memory_vault_promoted.py
"""
import os, sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime import memory as m   # noqa: E402


def test_response_interpretation_via_fake_post():
    calls = []
    orig = m._post
    m._post = lambda tool, pid, seat, params: calls.append((tool, params)) or {
        "palace_is_promoted": {"promoted": True, "promotedAt": "t"},
        "palace_mark_promoted": {"status": "ok", "key": params.get("key"), "upsert": "insert"},
        "palace_clear_promoted": {"status": "ok", "cleared": True},
    }[tool]
    try:
        assert m.is_promoted("pal", "aria", "k1") is True
        assert m.mark_promoted("pal", "aria", "k1", promoted_at="t") == {"status": "ok", "key": "k1"}
        assert m.clear_promoted("pal", "aria", "k1") == {"status": "ok", "cleared": True}
        # marshalling: mark carries promotedAt only when given; key always present
        assert ("palace_mark_promoted", {"key": "k1", "promotedAt": "t"}) in calls
        assert ("palace_is_promoted", {"key": "k1"}) in calls
    finally:
        m._post = orig
    print("PASS test_response_interpretation_via_fake_post")


def test_is_promoted_false_when_absent():
    orig = m._post
    m._post = lambda *a, **k: {"promoted": False}
    try:
        assert m.is_promoted("pal", "aria", "nope") is False
    finally:
        m._post = orig
    print("PASS test_is_promoted_false_when_absent")


def test_live_path_is_credential_gated():
    saved = {k: os.environ.pop(k, None) for k in ("CONVEX_DEPLOYMENT_URL", "CONVEX_SITE_URL")}
    try:
        for call in (lambda: m.is_promoted("t", "aria", "k"),
                     lambda: m.mark_promoted("t", "aria", "k"),
                     lambda: m.clear_promoted("t", "aria", "k")):
            try:
                call(); assert False, "expected MemPalaceError without creds"
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
    print("ALL VAULT-PROMOTED CLIENT TESTS PASS")
