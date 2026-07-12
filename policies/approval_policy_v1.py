"""approval-policy-v1 — the concrete dogfood `policy_config` artifact (P2 governance flip).

This is the DATA the governance flip sets for the dogfood tenant, encoded verbatim from the spec
`docs/decisions/approval-policy-v1.md` §3. It is a `.py` literal, NOT `.json`, ON PURPOSE — the engine
keys `overrides`/`hard_deny` on **tuple** `(scope, name)` keys, which JSON cannot represent (the .md:
"the engine takes tuple keys for `overrides`/`hard_deny`, so this is a `.py` literal, not JSON").

This module holds ONLY the policy; the loader (`acp.approval_policy_v1`) turns it into an
`acp.approval.ApprovalPolicy` / feeds it to `runtime.approval_gate.build_approval`. No logic here, no
imports — a data file the loader reads. Do not add rules here that are not in the .md; the .md is the spec.
"""
from __future__ import annotations

# Verbatim from approval-policy-v1.md §3 — the v1 dogfood policy_config.
APPROVAL_POLICY_V1 = {
    # Conservative spine: anything not explicitly allowed/denied below AWAITS a human (§4 fail-conservative).
    "default_mode": "ask",

    # Per-scope defaults (§3).
    "scope_modes": {
        "plan":    "ask",     # a whole plan pauses once, before the loop (cheap, one decision)
        "tool":    "ask",     # tools await unless an override allows the reversible ones
        "neop":    "allow",   # routing to a NEop is in-tenant + reversible
        "command": "deny",    # raw shell is off by default (the container jail is the sandbox, not policy)
    },

    # ALLOW — reversible, in-tenant, in-scope (the working surface, §1 ALLOW tier).
    "overrides": {
        ("tool", "palace_search"):   "allow",   # reads / retrieval
        ("tool", "palace_remember"): "allow",   # in-tenant reversible mutation (own scope)
        ("tool", "palace_get_twin"): "allow",   # own-twin (B2 carve-out)
        ("tool", "palace_put_twin"): "allow",   # own-twin (B2 carve-out)
        # external_send / cross-seat-write / spend-over-floor inherit scope default "ask" (AWAIT), §1.
    },

    # DENY — hard, non-overridable (GW-5). Irreversible and/or cross-tenant (§1 DENY tier); a human
    # grant CANNOT release these (re-checked at resume, `resolve_grant`).
    "hard_deny": {
        ("tool", "palace_delete"),          # data deletion / destructive mutation
        ("tool", "cross_tenant_write"),     # the isolation boundary itself (cross-TENANT write)
        ("tool", "secret_read"),            # secret access
        ("neop", "governance_disable"),     # disabling governance (the approval/audit machinery)
        ("tool", "egress_unallowlisted"),   # unallowlisted egress
    },
}
