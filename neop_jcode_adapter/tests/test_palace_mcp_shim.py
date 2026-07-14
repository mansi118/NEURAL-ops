"""T1 acceptance tests for palace_mcp_shim — the tenant chokepoint.

Targets the plan's must-pass set (§4 T1, §5):
  * model-supplied scope rejected 100%
  * non-allowlisted tool rejected
  * signing valid (round-trip verify)
  * fail-closed on blank scope (would otherwise default to _admin server-side)
  * correct real /mcp envelope shape (args under params; X-Palace-Neop header)

The scope/allowlist/fail-closed tests are pure stdlib. The signing test skips cleanly if
`cryptography` is not installed, so the security core is always graded.
"""
import json

import pytest

from neop_jcode_adapter import palace_mcp_shim as shim_mod
from neop_jcode_adapter.palace_mcp_shim import (
    PalaceShim,
    ScopeNotConfigured,
    ScopeSpoofRejected,
    ToolRejected,
    _canonical,
    _identity_claim,
    handle_message,
    run_stdio,
)

PAL = "pal_test"
SEAT = "aria"
URL = "https://small-dogfish-433.convex.site/mcp"


def make_shim(**kw):
    """Shim with an in-memory transport + audit collector (no network)."""
    sent = []
    audits = []

    def transport(url, body, headers):
        sent.append((url, body, headers))
        return 200, {"status": "ok", "data": {"echo": body["tool"]}}

    defaults = dict(
        palace_url=URL, palace_id=PAL, neop_id=SEAT, transport=transport, audit=audits.append
    )
    defaults.update(kw)
    s = PalaceShim(**defaults)
    return s, sent, audits


# ── fail-closed on blank scope ────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [dict(palace_id=""), dict(neop_id=""), dict(palace_url="")])
def test_blank_scope_refuses_to_construct(bad):
    base = dict(palace_url=URL, palace_id=PAL, neop_id=SEAT)
    base.update(bad)
    with pytest.raises(ScopeNotConfigured):
        PalaceShim(**base)


def test_whitespace_scope_also_refuses():
    with pytest.raises(ScopeNotConfigured):
        PalaceShim(palace_url=URL, palace_id="   ", neop_id=SEAT)


# ── allowlist ─────────────────────────────────────────────────────────────────
def test_allowlisted_tools_pass():
    s, _, _ = make_shim()
    for t in ("palace_search", "palace_remember"):
        body, _ = s.build_request(t, {"query": "x"})
        assert body["tool"] == t


def test_non_allowlisted_tool_rejected():
    s, _, _ = make_shim()
    for t in ("palace_delete", "shell", "fs_read", "palace_remember_all"):
        with pytest.raises(ToolRejected):
            s.build_request(t, {})


def test_get_closet_gated_by_default_then_enabled():
    s, _, _ = make_shim()
    with pytest.raises(ToolRejected):
        s.build_request("palace_get_closet", {"closetId": "c1"})
    s2, _, _ = make_shim(enable_get_closet=True)
    body, _ = s2.build_request("palace_get_closet", {"closetId": "c1"})
    assert body["tool"] == "palace_get_closet"


# ── scope-spoof: 100% rejection ───────────────────────────────────────────────
@pytest.mark.parametrize("key", ["palaceId", "neopId", "tool", "params"])
def test_model_supplied_scope_rejected(key):
    s, _, _ = make_shim()
    with pytest.raises(ScopeSpoofRejected):
        s.build_request("palace_search", {"query": "x", key: "evil"})


def test_scope_always_from_env_never_args():
    s, sent, _ = make_shim()
    # even a benign-looking arg cannot move scope; legit args land under params untouched
    s.call("palace_remember", {"content": "hello", "wingName": "team"})
    _, body, headers = sent[0]
    assert body["palaceId"] == PAL and body["neopId"] == SEAT
    assert body["params"] == {"content": "hello", "wingName": "team"}
    assert headers["X-Palace-Neop"] == SEAT  # defense-in-depth duplicate; never blank → no _admin


# ── real /mcp envelope shape (verified contract) ──────────────────────────────
def test_envelope_shape_matches_real_mcp():
    s, _, _ = make_shim()
    body, headers = s.build_request("palace_search", {"query": "neuraledge", "limit": 5})
    assert set(body) == {"tool", "palaceId", "neopId", "params"}
    assert body["params"] == {"query": "neuraledge", "limit": 5}
    assert headers["Content-Type"] == "application/json"


def test_call_returns_response_and_audits_once():
    s, sent, audits = make_shim()
    out = s.call("palace_search", {"query": "x"})
    assert out["http_status"] == 200 and out["response"]["status"] == "ok"
    assert len(sent) == 1 and len(audits) == 1
    # canonical audit record: action (not "tool"), result, scope on every line
    assert audits[0]["action"] == "palace_search" and audits[0]["result"] == "allow"
    assert audits[0]["neopId"] == SEAT and audits[0]["denied_at_layer"] is None


def test_denials_are_audited_with_layer():
    # both shim-level refusals produce a deny audit row BEFORE raising — leak detection needs it.
    s, _, audits = make_shim()
    with pytest.raises(ToolRejected):
        s.call("shell", {"cmd": "x"})
    with pytest.raises(ScopeSpoofRejected):
        s.call("palace_search", {"query": "x", "neopId": "recon"})
    assert [a["result"] for a in audits] == ["deny", "deny"]
    assert all(a["denied_at_layer"] == "adapter_shim" for a in audits)
    assert audits[1]["reason"] == "scope_spoof" and audits[1]["target"]["attempted_keys"] == ["neopId"]


def test_palace_403_audited_as_convex_sot_deny():
    audits = []

    def deny_transport(url, body, headers):
        return 403, {"status": "error", "error": "cross-seat denied"}

    s = PalaceShim(palace_url=URL, palace_id=PAL, neop_id=SEAT, transport=deny_transport, audit=audits.append)
    s.call("palace_search", {"query": "x"})
    assert audits[0]["result"] == "deny" and audits[0]["denied_at_layer"] == "convex_sot"


# ── signing (skips if cryptography absent) ────────────────────────────────────
def test_signing_round_trips_and_verifies():
    crypto = pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    signer = shim_mod.Ed25519Signer.generate()
    # inject the signer directly (bypass keyref resolution)
    s, _, _ = make_shim()
    s._signer = signer
    body, headers = s.build_request("palace_search", {"query": "x"})
    assert "X-NEop-Signature" in headers and "X-NEop-Pubkey" in headers
    pub = Ed25519PublicKey.from_public_bytes(shim_mod._unb64(headers["X-NEop-Pubkey"]))
    # verify() raises on a bad signature; passes silently on a good one
    pub.verify(shim_mod._unb64(headers["X-NEop-Signature"]), _canonical(body))
    # tamper → must fail
    with pytest.raises(Exception):
        tampered = dict(body, palaceId="other")
        pub.verify(shim_mod._unb64(headers["X-NEop-Signature"]), _canonical(tampered))


def test_identity_claim_verifies_and_binds_scope_and_tool():
    """Gate D: X-NEop-Identity signs (palaceId, neopId, tool) — the canonicalization-safe claim the
    palace verifies. It must verify against the pubkey and fail if ANY of the three bytes are altered."""
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    s, _, _ = make_shim()
    s._signer = shim_mod.Ed25519Signer.generate()
    _, headers = s.build_request("palace_search", {"query": "x"})
    assert "X-NEop-Identity" in headers and "X-NEop-Pubkey" in headers
    pub = Ed25519PublicKey.from_public_bytes(shim_mod._unb64(headers["X-NEop-Pubkey"]))
    # good claim verifies (matches the exact bytes the server will reconstruct)
    pub.verify(shim_mod._unb64(headers["X-NEop-Identity"]), _identity_claim(PAL, SEAT, "palace_search"))
    # a forged seat / palace / tool in the reconstructed claim must fail
    for bad in (_identity_claim(PAL, "recon", "palace_search"),
                _identity_claim("pal_other", SEAT, "palace_search"),
                _identity_claim(PAL, SEAT, "palace_remember")):
        with pytest.raises(Exception):
            pub.verify(shim_mod._unb64(headers["X-NEop-Identity"]), bad)


def test_no_signer_means_no_signature_headers_but_still_functional():
    s, sent, _ = make_shim()  # no signing_key_ref → no signer
    body, headers = s.build_request("palace_search", {"query": "x"})
    assert "X-NEop-Signature" not in headers
    assert "X-NEop-Identity" not in headers
    assert body["palaceId"] == PAL  # scope still enforced


# ── MCP stdio dispatch ────────────────────────────────────────────────────────
def test_tools_list_advertises_only_allowlisted():
    s, _, _ = make_shim()
    resp = handle_message(s, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"palace_search", "palace_remember"}


def test_tools_call_forbidden_tool_returns_iserror_not_crash():
    s, _, _ = make_shim()
    resp = handle_message(
        s,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "shell", "arguments": {"cmd": "rm -rf /"}}},
    )
    assert resp["result"]["isError"] is True


def test_run_stdio_end_to_end_with_string_streams():
    import io

    s, sent, _ = make_shim()
    inp = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                      "params": {"name": "palace_search", "arguments": {"query": "x"}}}) + "\n"
    )
    out = io.StringIO()
    run_stdio(s, stdin=inp, stdout=out)
    lines = [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]
    # initialize reply + tools/call reply (the notification produces no reply)
    assert len(lines) == 2
    assert lines[0]["result"]["serverInfo"]["name"] == "cortex-palace-shim"
    assert lines[1]["result"]["isError"] is False
    assert len(sent) == 1  # the search reached the transport
