"""Gate C — broker call-site seat-scope guard (Layer 4, defense in depth). Offline.

The Convex SoT (Gates A/B) is the authoritative seat-isolation enforcer. The broker's
job at Layer 4 is NOT to mirror room ownership (that would duplicate the SoT) but to
fail closed on a malformed identity BEFORE anything reaches the wire — a blank neopId
would otherwise default to "_admin" server-side (convex/http.ts) — and to surface a
server ACL denial as a TYPED, layer-attributed error (denied_at_layer=convex_sot).

All offline: the identity guard refuses before any network call; the denial-classification
path is exercised by monkeypatching urlopen. Stdlib only, no pytest.
Run: python3 tests/test_memory_scope.py   (exits non-zero on failure).
"""
import io, os, sys, pathlib, urllib.request, urllib.error
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime import memory as m   # noqa: E402

TWIN = {"twin_id": "neuraledge:aria", "version": 1, "maturity": "seed"}
REC = {"content": "x", "title": "t", "context": "c"}

# Every public entrypoint funnels through _post → _require_scope.
BLANK_CALLS = lambda tenant, seat: (
    ("retrieve", lambda: m.retrieve(tenant, seat, "q")),
    ("write",    lambda: m.write(tenant, seat, REC)),
    ("get_twin", lambda: m.get_twin(tenant, seat)),
    ("put_twin", lambda: m.put_twin(tenant, seat, TWIN)),
)


def _with_env(env, fn):
    saved = {k: os.environ.get(k) for k in env}
    try:
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return fn()
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def test_refuses_blank_seat_before_network():
    """A blank seat must be refused at the broker, tagged denied_at_layer=broker, even
    though a Convex URL is configured — proving the refusal precedes the network call."""
    def body():
        for blank in ("", "   ", None):
            for name, call in BLANK_CALLS("neuraledge", blank):
                try:
                    call()
                    assert False, f"{name}: expected refusal for blank seat {blank!r}"
                except m.MemPalaceError as e:
                    assert "denied_at_layer=broker" in str(e), f"{name}: {e}"
                    assert "seat/neopId" in str(e), f"{name}: {e}"
    _with_env({"CONVEX_SITE_URL": "https://dummy.convex.site",
               "CONVEX_DEPLOYMENT_URL": None}, body)
    print("PASS test_refuses_blank_seat_before_network")


def test_refuses_blank_tenant_before_network():
    def body():
        for blank in ("", "  ", None):
            for name, call in BLANK_CALLS(blank, "aria"):
                try:
                    call()
                    assert False, f"{name}: expected refusal for blank tenant {blank!r}"
                except m.MemPalaceError as e:
                    assert "denied_at_layer=broker" in str(e), f"{name}: {e}"
                    assert "tenant/palaceId" in str(e), f"{name}: {e}"
    _with_env({"CONVEX_SITE_URL": "https://dummy.convex.site",
               "CONVEX_DEPLOYMENT_URL": None}, body)
    print("PASS test_refuses_blank_tenant_before_network")


def test_valid_identity_passes_guard_and_hits_cred_gate():
    """A valid identity must pass the scope guard untouched — with creds removed it then
    fails at the credential gate, NOT at the broker scope guard (guard is a no-op here)."""
    def body():
        for name, call in BLANK_CALLS("neuraledge", "aria"):
            try:
                call()
                assert False, f"{name}: expected MemPalaceError without creds"
            except m.MemPalaceError as e:
                assert "denied_at_layer=broker" not in str(e), f"{name}: guard wrongly fired: {e}"
                assert "CONVEX_SITE_URL not set" in str(e), f"{name}: {e}"
    _with_env({"CONVEX_SITE_URL": None, "CONVEX_DEPLOYMENT_URL": None}, body)
    print("PASS test_valid_identity_passes_guard_and_hits_cred_gate")


def _fake_http_error(code, payload):
    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(
            "https://dummy.convex.site/mcp", code, "err", {}, io.BytesIO(payload))
    return _raise


def _with_urlopen(fake, fn):
    saved = urllib.request.urlopen
    urllib.request.urlopen = fake
    try:
        return fn()
    finally:
        urllib.request.urlopen = saved


def test_server_403_classified_as_convex_sot_denial():
    """A server 403 (seat isolation, Gates A/B) surfaces as a typed broker error tagged
    denied_at_layer=convex_sot — not a raw urllib.error.HTTPError."""
    def body():
        fake = _fake_http_error(403, b'{"status":"error","error":"access_denied: aria \\u2014 own room"}')
        def run():
            try:
                m.write("neuraledge", "aria", REC)
                assert False, "expected MemPalaceError on 403"
            except m.MemPalaceError as e:
                assert "denied_at_layer=convex_sot" in str(e), e
                assert "403" in str(e), e
            except urllib.error.HTTPError:
                assert False, "403 leaked as raw HTTPError — must be classified"
        _with_urlopen(fake, run)
    _with_env({"CONVEX_SITE_URL": "https://dummy.convex.site",
               "CONVEX_DEPLOYMENT_URL": None}, body)
    print("PASS test_server_403_classified_as_convex_sot_denial")


def test_non_403_http_error_not_tagged_as_denial():
    """A 500 is a transport error, NOT an ACL denial — must not carry denied_at_layer."""
    def body():
        fake = _fake_http_error(500, b"boom")
        def run():
            try:
                m.retrieve("neuraledge", "aria", "q")
                assert False, "expected MemPalaceError on 500"
            except m.MemPalaceError as e:
                assert "denied_at_layer" not in str(e), f"500 wrongly tagged as denial: {e}"
                assert "mempalace_http_error" in str(e) and "500" in str(e), e
        _with_urlopen(fake, run)
    _with_env({"CONVEX_SITE_URL": "https://dummy.convex.site",
               "CONVEX_DEPLOYMENT_URL": None}, body)
    print("PASS test_non_403_http_error_not_tagged_as_denial")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL GATE-C BROKER SCOPE TESTS PASS")
