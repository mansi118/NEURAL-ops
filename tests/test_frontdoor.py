"""Front-door (P5) tests — gateway, orchestrator (COC-1..5), loader, round-trip,
identity threading (run seat = routed NEop, NOT the human requester), rate-limit.
Stdlib only, offline. Run: python3 tests/test_frontdoor.py
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
def test_gateway_429_per_requester():
    rl = gateway.RateLimiter()
    for _ in range(60):
        rl.check("neuraledge", "ml", 0)            # throttle is per human requester
    try:
        rl.check("neuraledge", "ml", 0)
        assert False, "expected 429"
    except gateway.RateLimited as e:
        assert e.http == 429
    print("PASS test_gateway_429_per_requester")


def test_rate_concurrency_counter():
    # 16 concurrent/tenant — a DETERMINISTIC in-flight counter, not real async.
    rl = gateway.RateLimiter()
    for _ in range(16):
        rl.enter("neuraledge")
    try:
        rl.check("neuraledge", "ml", 0)
        assert False, "expected concurrency 429"
    except gateway.RateLimited as e:
        assert e.http == 429 and "concurrent" in str(e)
    print("PASS test_rate_concurrency_counter")


def test_gateway_auth_reject():
    try:
        gateway.authenticate({"channel": "matrix", "user_id": "x:y", "text": "hi"})  # no token/hmac
        assert False, "expected AuthError"
    except gateway.AuthError:
        pass
    print("PASS test_gateway_auth_reject")


def test_envelope_and_requester():
    env = gateway.normalize(raw("neuraledge:ml", "hello"))
    assert env["tenant_id"] == "neuraledge" and env["user_id"] == "neuraledge:ml"
    assert gateway.resolve_identity(env) == ("neuraledge", "ml")   # (tenant, requester) — NOT a run seat
    print("PASS test_envelope_and_requester")


# --- Gate 2: COC rules -------------------------------------------------------
def test_coc4_direct_mention_bypass():
    d = route(gateway.normalize(raw("neuraledge:ml", "hey @recon find leads")), CLASSIFIER)
    assert d["action"] == "dispatch" and d["neop"] == "recon" and "COC-4" in d["reason"]
    print("PASS test_coc4_direct_mention_bypass")


def test_coc23_confidence_gate():
    hi = route(gateway.normalize(raw("neuraledge:ml", "find leads")), CLASSIFIER)
    lo = route(gateway.normalize(raw("neuraledge:ml", "uh something")), CLASSIFIER)
    assert hi["action"] == "dispatch" and hi["neop"] == "recon"
    assert lo["action"] == "disambiguate" and lo["confidence"] < 0.7
    print("PASS test_coc23_confidence_gate")


def test_coc5_chain_guard():
    refused = route(gateway.normalize(raw("neuraledge:ml", "write a proposal")), CLASSIFIER)
    assert refused["action"] == "refuse" and "COC-5" in refused["reason"]
    ok = route(gateway.normalize(raw("neuraledge:ml", "write a proposal",
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


# --- Gate 3 (the pin) + 5: round-trip, run-seat semantic, latency boundary --
def test_roundtrip_echo():
    r = handle(raw("neuraledge:ml", "hello there"), CLASSIFIER, builtin_root=AGENTS)
    assert r["type"] == "response" and r["neop"] == "echo" and r["state"] == "DONE"
    # run seat = the routed NEop (echo); requester (ml) rides along, is NOT the seat
    assert r["seat"] == "echo" and r["requester"] == "ml" and r["tenant"] == "neuraledge"
    assert r["dispatched_msg"]["seat"] == "echo" and r["dispatched_msg"]["requester"] == "ml"
    assert "hello" in " ".join(r["stream"])
    assert r["overhead_ms"] < 800   # a measured FLOOR (excludes dispatch); the p50<=800/p95<=2s SLO is integration
    print("PASS test_roundtrip_echo")


def test_run_seat_is_routed_neop_not_requester():
    # THE PIN: a human requester (ml) invokes @cortex. The run must key on cortex
    # (its own memory), NOT on the human ml. Requester rides along as attribution only.
    r = handle(raw("neuraledge:ml", "@cortex what embeddings"), CLASSIFIER, builtin_root=AGENTS)
    assert r["type"] == "response" and r["neop"] == "cortex" and r["state"] == "DONE"
    assert r["seat"] == "cortex" and r["requester"] == "ml"          # seat != requester
    written = r["result"]["memory"]["written"]
    assert written, "cortex should have written memory"
    prov = written[0]["provenance"]
    assert prov["author_id"] == "cortex", f"memory must key on routed NEop, got {prov['author_id']}"
    assert prov["author_id"] != "ml", "must NOT key on the human requester (cross-wiring)"
    assert written[0]["tenant"] == "neuraledge"
    print("PASS test_run_seat_is_routed_neop_not_requester")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL FRONT-DOOR TESTS PASS")
