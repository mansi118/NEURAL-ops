# Decision — Approval policy v1 (the dogfood governance flip)

**Status: ACCEPTED (P2).** This is the concrete `policy_config` the governance flip sets for the
dogfood tenant. It drops straight into `build_approval(policy_config=…)` (→ `ApprovalPolicy(**config)`,
`acp/approval.py`). Turning governance ON is supplying this config; OFF is passing nothing
(`dispatch(approval=None)` is byte-identical). See the wired seam in `runtime/approval_gate.py` and the
ledger entry P2. The engine logic (GW-4/5/6) is already built + tested; this doc is the **policy**, not code.

## The shape the engine consumes (not aspirational — exact)
`decide(action, policy)` keys on `(scope, name)` with precedence **hard_deny (GW-5, non-overridable) >
per-`(scope,name)` override > per-`scope` default (`scope_modes`) > `default_mode`**. Scopes are
`command | tool | neop | plan`. Modes are `allow | deny | ask` (`ask` → AWAIT → the durable
`AwaitingApproval` pause + Decision Queue). So a policy is exactly: a conservative default, per-scope
defaults, a few exact-name overrides, and a hard-deny set.

## §1 — The three tiers (intent → how v1 realizes it)

**DENY — hard, non-overridable (GW-5). Irreversible AND/OR cross-tenant.** Not even a human grant can
release these (a grant re-checks hard_deny on resume — `resolve_grant`). The category:
- data **deletion** / destructive mutation,
- **cross-TENANT** writes (the isolation boundary itself),
- **secret** access,
- **disabling governance** (turning the approval/audit machinery off),
- **unallowlisted egress**.

**AWAIT — human approval (the Decision Queue).** Reversible-ish but consequential or outward-facing:
- **external send** (a message/email/post leaving the system),
- **cross-SEAT write** (within the tenant, touching another seat's state),
- **spend over a floor** (cost/quota above a threshold).

**ALLOW — reversible, in-tenant, in-scope.** The default working surface:
- reads / retrieval,
- internal drafts,
- **own-twin** access (the B2 carve-out — twin is identity, exact server-derived `neopId`; see
  `twin-keying.md`),
- in-scope reversible mutations.

**The cross-TENANT (DENY) vs cross-SEAT (ASK) split is deliberate, not an oversight.** The tenant boundary
is the isolation invariant the whole 4-layer ACL exists to hold — crossing it is never a judgment call, so
it is hard-denied below the human. A cross-seat action is inside one tenant's trust domain — consequential
enough to pause for a human, but a legitimate human grant can release it. Different blast radius ⇒
different tier.

## §2 — The grantor (named forward-dependency, not hidden)
A grant records the granting **authority** (`granted_by`). `build_approval` deliberately does NOT default
the grantor — a hardcoded grantor is an *asserted* identity, the exact thing scope-from-the-row and
server-derived-`requester` made unrepresentable everywhere else. **v1 is single-grantor dogfood:** the
operator passes its identity explicitly at construction. **The moment there is >1 granter, the grantor MUST
be server-derived from the Decision-Queue grant action's verified identity, threaded per-grant at resolve
time — never baked.** Pin this in the PR + ledger when multi-grantor lands. (Same managed-not-hidden shape
as single-writer Convex and Gate-D twin keying.)

## §3 — The concrete `policy_config` (v1 dogfood)
Python (the engine takes tuple keys for `overrides`/`hard_deny`, so this is a `.py` literal, not JSON):

```python
APPROVAL_POLICY_V1 = {
    # Conservative spine: anything not explicitly allowed/denied below AWAITS a human.
    "default_mode": "ask",

    # Per-scope defaults.
    "scope_modes": {
        "plan":    "ask",     # a whole plan pauses once, before the loop (cheap, one decision)
        "tool":    "ask",     # tools await unless an override allows the reversible ones
        "neop":    "allow",   # routing to a NEop is in-tenant + reversible
        "command": "deny",    # raw shell is off by default (the container jail is the sandbox, not policy)
    },

    # ALLOW — reversible, in-tenant, in-scope (the working surface).
    "overrides": {
        ("tool", "palace_search"):   "allow",   # reads
        ("tool", "palace_remember"): "allow",   # in-tenant reversible mutation (own scope)
        ("tool", "palace_get_twin"): "allow",   # own-twin (B2 carve-out)
        ("tool", "palace_put_twin"): "allow",   # own-twin (B2 carve-out)
        # external_send / cross-seat-write / spend-over-floor inherit scope default "ask" (AWAIT).
    },

    # DENY — hard, non-overridable (GW-5). Irreversible and/or cross-tenant.
    "hard_deny": {
        ("tool", "palace_delete"),          # data deletion / destructive
        ("tool", "cross_tenant_write"),     # the isolation boundary itself
        ("tool", "secret_read"),            # secret access
        ("neop", "governance_disable"),     # disabling governance
        ("tool", "egress_unallowlisted"),   # unallowlisted egress
    },
}
```

Flip it on (integration):
```python
from runtime.approval_gate import build_approval
approval = build_approval(APPROVAL_POLICY_V1, mode="integration",
                          palace_id=PALACE_ID, grantor=OPERATOR_NEOP)   # grantor explicit — §2
```

## §4 — Why this is safe to ship as the flip
- **Fail-conservative:** `default_mode="ask"` ⇒ an un-enumerated action AWAITS; it never silently allows.
- **The boundary is below the human:** cross-tenant / delete / secret / governance-off / unallowlisted
  egress are hard_deny — a grant can't release them (re-checked at resume).
- **Additive + reversible flip:** governance OFF (`approval=None`) is byte-identical to today; the flip is
  config, the seam is already live-proven (AwaitingApproval ↔ `paused_runs`, Decision Queue loop).

## §5 — v1 limits (named, not silently absent)
- **Exact-`(scope,name)` matching only — no predicates/attributes.** "Cross-tenant write" / "external
  send" / "spend over a floor" are *intent categories*; v1 realizes them as **enumerated names + the
  conservative `default_mode="ask"`** for the long tail. Attribute-aware matching (e.g. "any write whose
  target tenant ≠ caller tenant", "spend > $X") is a v2 evaluator, not a config bump.
- **No per-role policies** — one policy per tenant, not per seat/role.
- **No learned thresholds** — the spend floor and the await/allow lines are set, not learned.
- **No grant delegation** — a grantor can't delegate granting authority (ties to §2: single-grantor first).
- **Tool/command names above are the v1 vocabulary** — they must match the live tool registry when the flip
  is set; verify against the registry at flip time (the names are the contract).
