"""P2 — best-effort external-denial emit (broker layer → unified audit). Offline.
Run: python3 tests/test_audit_emit.py"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runtime import audit_emit as AE  # noqa: E402

AE._SYNC = True   # emits run inline + deterministic under test (prod dispatches off the critical path)


def test_noop_without_config():
    for k in ("CONVEX_DENIAL_SINK_URL", "PALACE_BRIDGE_API_KEY"):
        os.environ.pop(k, None)
    AE.emit_external_denial("palaceX", "broker", reason="x")   # must not raise, no network
    print("PASS test_noop_without_config")


def test_noop_blank_palace():
    saved = dict(os.environ)
    os.environ["CONVEX_DENIAL_SINK_URL"] = "http://sink.example"
    os.environ["PALACE_BRIDGE_API_KEY"] = "k"
    posted = []
    orig = AE.urllib.request.urlopen
    AE.urllib.request.urlopen = lambda *a, **k: posted.append(1)
    try:
        AE.emit_external_denial("   ", "broker", reason="blank palace")   # blank palace ⇒ cannot key ⇒ no-op
        assert not posted, "blank palaceId must not emit"
    finally:
        AE.urllib.request.urlopen = orig
        os.environ.clear(); os.environ.update(saved)
    print("PASS test_noop_blank_palace")


def test_posts_expected_payload_when_configured():
    saved = dict(os.environ)
    os.environ["CONVEX_DENIAL_SINK_URL"] = "http://sink.example"
    os.environ["PALACE_BRIDGE_API_KEY"] = "secret"
    cap = {}

    class _R:
        def close(self):
            pass

    def fake(req, timeout=None):
        cap["url"] = req.full_url
        cap["key"] = req.get_header("X-palace-key")
        cap["body"] = json.loads(req.data.decode())
        return _R()

    orig = AE.urllib.request.urlopen
    AE.urllib.request.urlopen = fake
    try:
        AE.emit_external_denial("palaceX", "broker", neop_id="  ", reason="blank seat")
    finally:
        AE.urllib.request.urlopen = orig
        os.environ.clear(); os.environ.update(saved)
    assert cap["url"] == "http://sink.example/external-denial"
    assert cap["key"] == "secret"
    assert cap["body"]["deniedAtLayer"] == "broker"
    assert cap["body"]["palaceId"] == "palaceX"
    assert cap["body"]["neopId"] == "unknown"      # blank seat normalized
    print("PASS test_posts_expected_payload_when_configured")


def test_edge_denial_resolves_palace_then_emits():
    saved = dict(os.environ)
    os.environ["CONVEX_DENIAL_SINK_URL"] = "http://sink.example"
    os.environ["PALACE_BRIDGE_API_KEY"] = "k"
    cap = {}

    class _R:
        def close(self):
            pass

    def fake(req, timeout=None):
        cap["body"] = json.loads(req.data.decode())
        return _R()

    class _Rej:
        audit = {"tenant": "neuraledge", "claimed": "_admin", "reason": "reserved_identity_claimed"}

    orig = AE.urllib.request.urlopen
    AE.urllib.request.urlopen = fake
    try:
        AE.emit_edge_denial(_Rej(), resolve_palace_id=lambda t: "palace123" if t == "neuraledge" else None)
    finally:
        AE.urllib.request.urlopen = orig
        os.environ.clear(); os.environ.update(saved)
    assert cap["body"]["deniedAtLayer"] == "edge"
    assert cap["body"]["palaceId"] == "palace123"   # resolved name→palaceId — the key the edge lacked
    assert cap["body"]["neopId"] == "_admin"
    print("PASS test_edge_denial_resolves_palace_then_emits")


def test_edge_denial_noop_when_no_tenant_or_unresolvable():
    AE.emit_edge_denial(type("R", (), {"audit": {}})(), resolve_palace_id=lambda t: "x")          # no tenant
    AE.emit_edge_denial(type("R", (), {"audit": {"tenant": "ghost"}})(), resolve_palace_id=lambda t: None)
    print("PASS test_edge_denial_noop_when_no_tenant_or_unresolvable")


def test_edge_auth_on_reject_seam_fires_and_enriches_tenant():
    from acp.edge_auth import resolve_edge_identity, EdgeRejected
    cap = []
    try:
        resolve_edge_identity(
            {"from": {}}, as_context={"mxid": "@x:host", "tenant_id": "neuraledge"},
            verify_hmac=lambda i: True, resolve_binding=lambda m: None,    # unknown user → EdgeRejected
            on_reject=lambda e: cap.append(e))
        assert False, "should have rejected"
    except EdgeRejected:
        pass
    assert cap and cap[0].audit["tenant"] == "neuraledge"   # enriched from the AS namespace for keying
    print("PASS test_edge_auth_on_reject_seam_fires_and_enriches_tenant")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL AUDIT-EMIT TESTS PASS")
