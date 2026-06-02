"""Front-door (P5) tests — gateway, orchestrator (COC-1..5), loader, round-trip,
identity threading, latency boundary. Stdlib only, offline. Run: python3 tests/test_frontdoor.py
"""
import sys, pathlib, tempfile
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from frontdoor import gateway, loader                      # noqa: E402
from frontdoor.orchestrator import recorded_classifier, route, handle  # noqa: E402

CLASSIFIER = recorded_classifier({
    "leads": ("recon", 0.9),
    "hello": ("echo", 0.95),
    "uh": ("echo", 0.4),
    "proposal": ("recon+researcher+proposal", 0.85),
})
AGENTS = str(R / "agents")


def raw(user_id, text, **kw):
    return {"channel": "matrix", "user_id": user_id, "text": text, "token": "t", "hmac": "h", **kw}


# --- Gate 1: gateway ---------------------------------------------------------
def test_gateway_429():
    rl = gateway.RateLimiter()
    for _ in range(60):
        rl.check("neuraledge", "aria", 0)
    try:
        rl.check("neuraledge", "aria", 0)
        assert False, "expected 429"
    except gateway.RateLimited as e:
        assert e.http == 429
    print("PASS test_gateway_429")


def test_gateway_auth_reject():
    try:
        gateway.authenticate({"channel": "matrix", "user_id": "x:y", "text": "hi"})  # no token/hmac
        assert False, "expected AuthError"
    except gateway.AuthError:
        pass
    print("PASS test_gateway_auth_reject")


def test_envelope_and_identity():
    env = gateway.normalize(raw("neuraledge:aria", "hello"))
    assert env["tenant_id"] == "neuraledge" and env["user_id"] == "neuraledge:aria"
    assert gateway.resolve_identity(env) == ("neuraledge", "aria")
    print("PASS test_envelope_and_identity")


# --- Gate 2: COC rules -------------------------------------------------------
def test_coc4_direct_mention_bypass():
    d = route(gateway.normalize(raw("neuraledge:aria", "hey @recon find leads")), CLASSIFIER)
    assert d["action"] == "dispatch" and d["neop"] == "recon" and "COC-4" in d["reason"]
    print("PASS test_coc4_direct_mention_bypass")


def test_coc23_confidence_gate():
    hi = route(gateway.normalize(raw("neuraledge:aria", "find leads")), CLASSIFIER)
    lo = route(gateway.normalize(raw("neuraledge:aria", "uh something")), CLASSIFIER)
    assert hi["action"] == "dispatch" and hi["neop"] == "recon"
    assert lo["action"] == "disambiguate" and lo["confidence"] < 0.7
    print("PASS test_coc23_confidence_gate")


def test_coc5_chain_guard():
    refused = route(gateway.normalize(raw("neuraledge:aria", "write a proposal")), CLASSIFIER)
    assert refused["action"] == "refuse" and "COC-5" in refused["reason"]
    ok = route(gateway.normalize(raw("neuraledge:aria", "write a proposal",
                                     metadata={"explicit_intent": True})), CLASSIFIER)
    assert ok["action"] == "dispatch"
    print("PASS test_coc5_chain_guard")


# --- Gate 4: loader resolution ----------------------------------------------
def test_loader_precedence():
    assert loader.resolve("echo", "neuraledge", builtin_root=AGENTS) == R / "agents" / "echo"
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        ov = td / "neuraledge" / "agents" / "echo"
        ov.mkdir(parents=True)
        (ov / "neop.md").write_text("---\nneop_id: echo\n---\n")
        got = loader.resolve("echo", "neuraledge", builtin_root=AGENTS, tenant_root=str(td))
        assert got == ov, f"tenant override must win, got {got}"
    assert loader.resolve("nope", "neuraledge", builtin_root=AGENTS) is None
    print("PASS test_loader_precedence")


# --- Gate 3 + 5: round-trip, identity threading, latency --------------------
def test_roundtrip_echo():
    r = handle(raw("neuraledge:aria", "hello there"), CLASSIFIER, builtin_root=AGENTS)
    assert r["type"] == "response" and r["neop"] == "echo" and r["state"] == "DONE"
    assert r["dispatched_msg"]["tenant"] == "neuraledge" and r["dispatched_msg"]["seat"] == "aria"
    assert "hello" in " ".join(r["stream"])
    assert r["overhead_ms"] < 800, f"non-agent overhead {r['overhead_ms']}ms over budget"
    print("PASS test_roundtrip_echo")


def test_identity_threads_to_brokers():
    # @cortex bypass -> cortex writes memory; provenance must carry the gateway-resolved (tenant, seat)
    r = handle(raw("neuraledge:aria", "@cortex what embeddings"), CLASSIFIER, builtin_root=AGENTS)
    assert r["type"] == "response" and r["neop"] == "cortex" and r["state"] == "DONE"
    written = r["result"]["memory"]["written"]
    assert written, "cortex should have written memory"
    assert written[0]["provenance"]["author_id"] == "aria", written[0]
    assert written[0]["tenant"] == "neuraledge", written[0]
    print("PASS test_identity_threads_to_brokers")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL FRONT-DOOR TESTS PASS")
