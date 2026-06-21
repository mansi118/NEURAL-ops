"""Edge authentication (#1/#3) — the gateway's identity layer (docs/edge-auth-spec.md).

Establishes WHO a message is from before the memory ACL decides WHAT it can touch. Identity
is NEVER trusted from the message body: the edge takes the credential-verified mxid + tenant
from the channel adapter / Application-Service context, looks up the binding (the ONLY source
of requester identity), and OVERWRITES the envelope identity with the bound values — or REFUSES.
Reserved identities (`_admin`/`_system`/`_*`) are server-minted only and can never enter from a
channel.

Layering: edge-auth governs the REQUESTER (the human, for attribution + authorization);
runtime/#2 governs the ACTOR (the routed NEop). Together neither identity is forgeable. This is
Layer 0 (identity) ahead of the four memory-ACL layers — the gateway's half of NFR-10.

Offline-gradeable (seam discipline, like the other five broker seams): `verify_hmac` and
`resolve_binding` are INJECTED — unit mode replays recorded fixtures; integration mode reaches
the live adapter HMAC + Convex binding store + Synapse AS, credential-gated. No live homeserver
is needed for CI-green. core.py untouched.
"""
from __future__ import annotations

RESERVED_PREFIX = "_"
# Explicit elevated identities (server-minted; mirror convex/lib/enums). The prefix rule below
# already covers these and any future `_x`; this set documents the known ones.
RESERVED_IDENTITIES = frozenset({"_admin", "_system"})

__all__ = [
    "RESERVED_IDENTITIES", "is_reserved_identity", "EdgeRejected",
    "assert_no_reserved_claim", "resolve_edge_identity",
]


def is_reserved_identity(identity) -> bool:
    """A reserved identity is SERVER-MINTED ONLY — never a valid channel-derived requester.
    Any `_`-prefixed actor is reserved (covers _admin/_system and future elevated ids)."""
    return isinstance(identity, str) and identity.strip().startswith(RESERVED_PREFIX)


class EdgeRejected(Exception):
    """An inbound refused at the edge. Carries an audit record tagged denied_at_layer=edge,
    so every refusal is measurable at the edge exactly as the 4-layer ACL is at the memory
    boundary. The audit record is produced here; routing it to the sink (Convex audit_events /
    nc-audit) is downstream (#12)."""

    def __init__(self, reason: str, *, claimed=None, mxid=None, tenant=None):
        self.reason = reason
        self.audit = {
            "denied_at_layer": "edge",
            "reason": reason,
            "claimed": claimed,
            "mxid": mxid,
            "tenant": tenant,
        }
        super().__init__(
            f"denied_at_layer=edge: {reason}"
            + (f" (claimed={claimed!r})" if claimed is not None else "")
        )


# ─── E2: reserved-identity refusal ───────────────────────────────────────────

def _claimed_identities(inbound: dict):
    """Every place a requester identity could be CLAIMED in an inbound — body `from.actor`,
    flat `user_id`, and payload/top-level mentions. The edge scans ALL of them: the claim can
    hide anywhere, and a reserved identity in any position is a refusal."""
    out = []
    frm = inbound.get("from")
    if isinstance(frm, dict):
        out.append(frm.get("actor"))
    out.append(inbound.get("user_id"))
    payload = inbound.get("payload")
    mentions = (payload.get("mentions") if isinstance(payload, dict) else None) \
        or inbound.get("mentions") or []
    if isinstance(mentions, (list, tuple)):
        out.extend(mentions)
    return [c for c in out if isinstance(c, str)]


def assert_no_reserved_claim(inbound: dict) -> None:
    """E2: refuse any inbound that CLAIMS a reserved identity anywhere. Raises EdgeRejected
    (audited). Relevant even single-tenant — it's the smallest, highest-value guard."""
    for c in _claimed_identities(inbound):
        if is_reserved_identity(c):
            raise EdgeRejected("reserved_identity_claimed_from_channel", claimed=c)


# ─── E3 (+ E4 tenant binding): edge resolver ─────────────────────────────────

def resolve_edge_identity(inbound, *, as_context, verify_hmac, resolve_binding):
    """Produce a canonical envelope whose identity is provably credential-derived.

      as_context:  {"mxid": <AS-verified>, "tenant_id": <from the delivering AS namespace>}
                   — sourced from the Application-Service, NEVER from the message body.
      verify_hmac(inbound) -> bool          — CA-4 per-adapter HMAC (seam).
      resolve_binding(mxid) -> binding|None — Convex SoT (seam); binding =
                   {tenant_id, seat_id, role, status}. The ONLY source of requester identity.

    Returns `inbound` with `from`/`user_id`/`tenant_id` OVERWRITTEN from the binding and
    `_identity_provenance="edge_bound"`. Raises EdgeRejected (audited) on any failure —
    overwrite-or-refuse, never pass-through; unknown ⇒ refuse, never default-to-a-seat.
    """
    # 1. CA-4 per-adapter HMAC — authenticate the adapter before trusting anything it carries.
    if not verify_hmac(inbound):
        raise EdgeRejected("bad_adapter_hmac")

    # 2. AS-verified identity (from the AS, not the body).
    mxid = (as_context or {}).get("mxid")
    tenant_from_as = (as_context or {}).get("tenant_id")
    if not (isinstance(mxid, str) and mxid.strip()):
        raise EdgeRejected("missing_as_verified_mxid")
    if not (isinstance(tenant_from_as, str) and tenant_from_as.strip()):
        raise EdgeRejected("missing_as_tenant")

    # 3. E2 — reject reserved-identity claims anywhere in the inbound, before binding.
    assert_no_reserved_claim(inbound)

    # 4. E1 lookup — the ONLY source of requester identity. Unknown ⇒ REFUSE (never default).
    binding = resolve_binding(mxid)
    if binding is None:
        raise EdgeRejected("unknown_user_no_binding", mxid=mxid)
    if (binding.get("status") or "active") != "active":
        raise EdgeRejected("binding_inactive", mxid=mxid)
    seat = binding.get("seat_id")
    tenant = binding.get("tenant_id")
    # Defense in depth: a binding must never map a human to a reserved identity (E1 rejects
    # this at write time; re-check so a corrupted store can't escalate a requester).
    if is_reserved_identity(seat):
        raise EdgeRejected("binding_to_reserved_identity", claimed=seat, mxid=mxid)

    # 5. E4 — tenant comes from the AS namespace; a cross-tenant mxid is rejected.
    if tenant != tenant_from_as:
        raise EdgeRejected("cross_tenant_mxid", mxid=mxid, tenant=tenant_from_as)

    # 6. OVERWRITE identity from the binding — discard anything the client carried.
    out = dict(inbound)
    frm = dict(out.get("from") or {})
    frm["tenant"] = tenant
    frm["actor"] = seat
    out["from"] = frm
    out["tenant_id"] = tenant
    out["user_id"] = seat
    out["_identity_provenance"] = "edge_bound"
    return out
