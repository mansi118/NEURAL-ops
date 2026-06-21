"""Approval mediation policy (P2 · GW-4/5/6) — the governance front-door's decision logic.

PURE + offline: given an action and a tenant's approval policy, decide ALLOW / DENY / AWAIT and
emit an audit record. This module is ONLY the policy the gateway consults; the `AwaitingApproval`
RUN-STATE (the executor blocking mid-run on AWAIT and resuming on a human grant) is the separate,
sanctioned `core.py` wiring. No core.py import, no network.

GW-4 — four approval scopes: command | tool | neop | plan.
GW-5 — a NON-OVERRIDABLE hard-deny list: not even a human grant can override it.
GW-6 — every decision (and every grant) produces an audit record (who·what·on-whom·permission·result).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

SCOPES = frozenset({"command", "tool", "neop", "plan"})

# Decisions.
ALLOW = "allow"
DENY = "deny"
AWAIT = "await"          # requires human approval (→ AwaitingApproval run-state, wired in core.py)

# Per-scope / per-name policy modes.
MODES = frozenset({"allow", "deny", "ask"})

__all__ = ["SCOPES", "ALLOW", "DENY", "AWAIT", "MODES", "Action", "ApprovalPolicy",
           "ApprovalError", "decide", "resolve_grant", "audit_record", "mediate"]


class ApprovalError(ValueError):
    pass


@dataclass(frozen=True)
class Action:
    """An action seeking authorization. `name` is the id within the scope (e.g. tool 'bash',
    neop 'recon', plan 'deploy'). `target` is the on-whom (optional, for audit)."""
    scope: str
    name: str
    seat: str
    tenant: str
    target: Optional[str] = None

    def __post_init__(self):
        if self.scope not in SCOPES:
            raise ApprovalError(f"unknown scope {self.scope!r} — must be one of {sorted(SCOPES)}")
        if not (isinstance(self.name, str) and self.name.strip()):
            raise ApprovalError("action.name required")


@dataclass
class ApprovalPolicy:
    """A tenant's approval configuration. `scope_modes` is the per-scope default; `overrides` is
    per-(scope,name); `hard_deny` is the non-overridable denylist (GW-5)."""
    scope_modes: dict = field(default_factory=dict)        # {scope: "allow"|"deny"|"ask"}
    overrides: dict = field(default_factory=dict)          # {(scope,name): mode}
    hard_deny: set = field(default_factory=set)            # {(scope,name)} — non-overridable
    default_mode: str = "ask"                              # unknown (scope) → conservative ASK

    def __post_init__(self):
        for m in list(self.scope_modes.values()) + list(self.overrides.values()) + [self.default_mode]:
            if m not in MODES:
                raise ApprovalError(f"invalid mode {m!r} — must be one of {sorted(MODES)}")

    def is_hard_denied(self, action: Action) -> bool:
        return (action.scope, action.name) in self.hard_deny

    def mode_for(self, action: Action) -> str:
        # precedence: per-(scope,name) override > per-scope default > policy default.
        return self.overrides.get((action.scope, action.name)) \
            or self.scope_modes.get(action.scope) \
            or self.default_mode


def decide(action: Action, policy: ApprovalPolicy):
    """Return (decision, reason). GW-5 hard-deny is checked FIRST and is non-overridable."""
    if policy.is_hard_denied(action):
        return DENY, "hard_deny: non-overridable denylist (GW-5)"
    mode = policy.mode_for(action)
    if mode == "allow":
        return ALLOW, "policy_allow"
    if mode == "deny":
        return DENY, "policy_deny"
    return AWAIT, "requires_approval"   # "ask"


def resolve_grant(action: Action, policy: ApprovalPolicy, *, granted_by: str):
    """A human grant on an AWAIT. Proceeds ONLY if not hard-denied — a grant can NEVER override GW-5."""
    if policy.is_hard_denied(action):
        return DENY, "hard_deny: a grant cannot override the non-overridable denylist (GW-5)"
    if not (isinstance(granted_by, str) and granted_by.strip()):
        raise ApprovalError("granted_by required for a grant")
    return ALLOW, f"approved_by:{granted_by}"


def audit_record(action: Action, decision: str, reason: str, *, granted_by: Optional[str] = None) -> dict:
    """GW-6 — the approval audit record (who·what·on-whom·permission·result). `when` is stamped at the sink."""
    return {
        "kind": "approval",
        "scope": action.scope,
        "name": action.name,
        "seat": action.seat,         # who (requester)
        "tenant": action.tenant,
        "target": action.target,     # on-whom
        "decision": decision,        # result
        "reason": reason,            # permission/basis
        "granted_by": granted_by,
    }


def mediate(action: Action, policy: ApprovalPolicy):
    """Decide + produce the audit record in one call → (decision, reason, audit)."""
    decision, reason = decide(action, policy)
    return decision, reason, audit_record(action, decision, reason)
