"""Edge authentication (#1/#3) — E2 reserved refusal, E3 resolver, E4 tenant binding,
E5 red-team gate. Offline, deterministic, no live homeserver (seams = recorded fixtures).
core untouched. Run: python3 tests/test_edge_auth.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from acp import edge_auth as EA  # noqa: E402

# Recorded binding store (E1 seam): mxid -> binding. The live store is Convex resolveBinding.
BINDINGS = {
    "@alice:neuraledge.org": {"tenant_id": "neuraledge", "seat_id": "aria", "role": "member", "status": "active"},
    "@bob:neuraledge.org":   {"tenant_id": "neuraledge", "seat_id": "recon", "role": "member", "status": "active"},
    "@susp:neuraledge.org":  {"tenant_id": "neuraledge", "seat_id": "scout", "role": "member", "status": "suspended"},
    "@evil:neuraledge.org":  {"tenant_id": "neuraledge", "seat_id": "_admin", "role": "admin", "status": "active"},  # corrupted store
}
RESOLVE = lambda mxid: BINDINGS.get(mxid)          # E1 seam (recorded)
HMAC_OK = lambda _inbound: True                     # CA-4 seam (recorded "verified")
HMAC_BAD = lambda _inbound: False
AS = lambda mxid, tenant="neuraledge": {"mxid": mxid, "tenant_id": tenant}


def _inbound(**over):
    base = {"from": {"tenant": "neuraledge", "actor": "anon", "type": "human"},
            "payload": {"text": "hi"}}
    base.update(over)
    return base


def _resolve(inbound, mxid="@alice:neuraledge.org", tenant="neuraledge", verify=HMAC_OK):
    return EA.resolve_edge_identity(inbound, as_context=AS(mxid, tenant),
                                    verify_hmac=verify, resolve_binding=RESOLVE)


def _expect_reject(fn, reason_sub):
    try:
        fn()
        assert False, f"expected EdgeRejected ({reason_sub})"
    except EA.EdgeRejected as e:
        assert e.audit["denied_at_layer"] == "edge", e.audit
        assert reason_sub in e.reason, f"reason {e.reason!r} lacks {reason_sub!r}"


# ─── E2: reserved-identity refusal ───────────────────────────────────────────

def test_is_reserved_identity():
    for r in ("_admin", "_system", "_x", " _admin", "_"):
        assert EA.is_reserved_identity(r), r
    for ok in ("aria", "recon", "neuralchat", "", None, 123):
        assert not EA.is_reserved_identity(ok), ok
    print("PASS test_is_reserved_identity")


def test_e2_reserved_claim_rejected_wherever_it_sits():
    # body from.actor
    _expect_reject(lambda: EA.assert_no_reserved_claim(_inbound(**{"from": {"actor": "_admin"}})),
                   "reserved_identity")
    # flat user_id
    _expect_reject(lambda: EA.assert_no_reserved_claim(_inbound(user_id="_system")), "reserved_identity")
    # a mention
    _expect_reject(lambda: EA.assert_no_reserved_claim(_inbound(payload={"mentions": ["aria", "_admin"]})),
                   "reserved_identity")
    # non-reserved everywhere → OK (no raise)
    EA.assert_no_reserved_claim(_inbound(user_id="aria", payload={"mentions": ["recon"]}))
    print("PASS test_e2_reserved_claim_rejected_wherever_it_sits")


# ─── E3: resolver overwrite + refusals ───────────────────────────────────────

def test_e3_happy_path_overwrites_identity_from_binding():
    out = _resolve(_inbound(), mxid="@alice:neuraledge.org")
    assert out["user_id"] == "aria" and out["tenant_id"] == "neuraledge", out
    assert out["from"]["actor"] == "aria" and out["from"]["tenant"] == "neuraledge", out
    assert out["_identity_provenance"] == "edge_bound", out
    print("PASS test_e3_happy_path_overwrites_identity_from_binding")


def test_e3_forged_user_id_is_overwritten_not_trusted():
    # The client claims to be a different human's seat; the bound mxid wins.
    out = _resolve(_inbound(user_id="cos", **{"from": {"actor": "cos", "tenant": "neuraledge"}}),
                   mxid="@bob:neuraledge.org")
    assert out["user_id"] == "recon", f"forged user_id leaked: {out['user_id']}"
    assert out["from"]["actor"] == "recon", out
    print("PASS test_e3_forged_user_id_is_overwritten_not_trusted")


def test_e3_unknown_user_refused_never_defaulted():
    _expect_reject(lambda: _resolve(_inbound(), mxid="@nobody:neuraledge.org"), "unknown_user_no_binding")
    print("PASS test_e3_unknown_user_refused_never_defaulted")


def test_e3_bad_hmac_refused():
    _expect_reject(lambda: _resolve(_inbound(), verify=HMAC_BAD), "bad_adapter_hmac")
    print("PASS test_e3_bad_hmac_refused")


def test_e3_missing_as_context_refused():
    _expect_reject(lambda: EA.resolve_edge_identity(_inbound(), as_context={"tenant_id": "neuraledge"},
                                                    verify_hmac=HMAC_OK, resolve_binding=RESOLVE),
                   "missing_as_verified_mxid")
    _expect_reject(lambda: EA.resolve_edge_identity(_inbound(), as_context={"mxid": "@alice:neuraledge.org"},
                                                    verify_hmac=HMAC_OK, resolve_binding=RESOLVE),
                   "missing_as_tenant")
    print("PASS test_e3_missing_as_context_refused")


def test_e3_suspended_binding_refused():
    _expect_reject(lambda: _resolve(_inbound(), mxid="@susp:neuraledge.org"), "binding_inactive")
    print("PASS test_e3_suspended_binding_refused")


# ─── E4: tenant from AS namespace, cross-tenant rejected ─────────────────────

def test_e4_cross_tenant_mxid_refused():
    # @alice is bound to tenant neuraledge; an AS claiming tenant "other" must be rejected.
    _expect_reject(lambda: _resolve(_inbound(), mxid="@alice:neuraledge.org", tenant="other"),
                   "cross_tenant_mxid")
    print("PASS test_e4_cross_tenant_mxid_refused")


def test_e4_tenant_never_from_body():
    # Body claims tenant "other"; bound tenant (neuraledge, from AS) wins.
    out = _resolve(_inbound(tenant_id="other", **{"from": {"actor": "x", "tenant": "other"}}),
                   mxid="@alice:neuraledge.org", tenant="neuraledge")
    assert out["tenant_id"] == "neuraledge" and out["from"]["tenant"] == "neuraledge", out
    print("PASS test_e4_tenant_never_from_body")


# ─── E5: red-team gate (spoof / forge / unknown / cross-tenant + corrupted store) ───

def test_e5_redteam_zero_bypasses():
    # spoof: claim a privileged seat
    _expect_reject(lambda: _resolve(_inbound(user_id="_admin"), mxid="@alice:neuraledge.org"),
                   "reserved_identity")
    # forge: claim another human's seat → overwritten (proven above); assert no leak here too
    out = _resolve(_inbound(user_id="forge-victim"), mxid="@bob:neuraledge.org")
    assert out["user_id"] == "recon"
    # unknown: no binding
    _expect_reject(lambda: _resolve(_inbound(), mxid="@ghost:neuraledge.org"), "unknown_user_no_binding")
    # cross-tenant: wrong homeserver/AS
    _expect_reject(lambda: _resolve(_inbound(), mxid="@alice:neuraledge.org", tenant="acme"),
                   "cross_tenant_mxid")
    # corrupted store: a binding that maps a human to a reserved seat must still be refused
    _expect_reject(lambda: _resolve(_inbound(), mxid="@evil:neuraledge.org"), "binding_to_reserved_identity")
    print("PASS test_e5_redteam_zero_bypasses")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL EDGE-AUTH TESTS PASS")
