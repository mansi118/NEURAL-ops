# approval-policy-v1 — Rego MIRROR of the Python approval engine (acp/approval.py `decide`).
#
# PARITY DOCUMENTATION, NOT a second source of truth. The Python engine is authoritative; this file
# expresses the SAME v1 dogfood rules (docs/decisions/approval-policy-v1.md §3) for the OPA/Rego
# sign-off the plan calls for. Precedence mirrors `ApprovalPolicy.mode_for` + `decide` exactly:
#   hard_deny (GW-5, non-overridable)  >  per-(scope,name) override  >  per-scope default  >  default_mode
# Modes map to decisions: allow -> "allow", deny -> "deny", ask -> "await" (the AwaitingApproval pause).
#
# Input:  {"scope": <command|tool|neop|plan>, "name": <str>}   (seat/tenant/target are audit-only, unused here)
# Output: data.neos.approval.decision  ∈ {"allow","deny","await"}   and  data.neos.approval.reason
#
# Query e.g.:  opa eval -d approval_policy_v1.rego -I 'data.neos.approval.decision'
package neos.approval

import rego.v1

# --- the v1 policy_config, verbatim from the .md §3 (tuple keys -> Rego array keys) -----------------
default_mode := "ask"

scope_modes := {
	"plan": "ask",
	"tool": "ask",
	"neop": "allow",
	"command": "deny",
}

overrides := {
	["tool", "palace_search"]: "allow", # reads / retrieval
	["tool", "palace_remember"]: "allow", # in-tenant reversible mutation (own scope)
	["tool", "palace_get_twin"]: "allow", # own-twin (B2 carve-out)
	["tool", "palace_put_twin"]: "allow", # own-twin (B2 carve-out)
}

hard_deny := {
	["tool", "palace_delete"], # data deletion / destructive mutation
	["tool", "cross_tenant_write"], # the isolation boundary itself
	["tool", "secret_read"], # secret access
	["neop", "governance_disable"], # disabling governance
	["tool", "egress_unallowlisted"], # unallowlisted egress
}

mode_to_decision := {
	"allow": "allow",
	"deny": "deny",
	"ask": "await",
}

# --- decision logic (mirrors acp/approval.decide) --------------------------------------------------
key := [input.scope, input.name]

hard_denied if key in hard_deny

# Effective mode when NOT hard-denied — precedence via else-chain: override > scope default > default.
mode_for := overrides[key] if {
	overrides[key]
} else := scope_modes[input.scope] if {
	scope_modes[input.scope]
} else := default_mode

# GW-5 first and non-overridable.
decision := "deny" if hard_denied

decision := mode_to_decision[mode_for] if not hard_denied

# Reason strings, aligned to the Python engine's `decide` return values (parity nicety; decision is
# the asserted field). hard_deny -> GW-5 reason; else policy_allow / policy_deny / requires_approval.
reason := "hard_deny: non-overridable denylist (GW-5)" if hard_denied

reason := "policy_allow" if {
	not hard_denied
	mode_for == "allow"
}

reason := "policy_deny" if {
	not hard_denied
	mode_for == "deny"
}

reason := "requires_approval" if {
	not hard_denied
	mode_for == "ask"
}
