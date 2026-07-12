"""approval-policy-v1 loader — turn the concrete artifact into something `build_approval` accepts.

The SPEC is `docs/decisions/approval-policy-v1.md`; the DATA is `policies/approval_policy_v1.py`
(`APPROVAL_POLICY_V1`, tuple-keyed — a `.py` literal because JSON can't hold `(scope, name)` keys).
This module is the seam between them: it reads the artifact and returns either the raw `policy_config`
dict or a constructed `acp.approval.ApprovalPolicy`, both of which `runtime.approval_gate.build_approval`
consumes (`build_approval` does `ApprovalPolicy(**config)` for a dict, or takes an instance as-is).

Scope this policy targets — the DOGFOOD tenant (`DOGFOOD_TENANT`). v1 is ONE policy per tenant (.md §5:
"No per-role policies — one policy per tenant, not per seat/role"), so this loader is intentionally
scope-free: the tenant/seat live on each `Action`, not on the policy. `build_approval(mode="integration")`
binds it to a concrete palace via `palace_id`; the flip also passes `grantor` explicitly (.md §2 —
single-grantor dogfood, never baked). PURE + offline: no core.py import, no network, no wall-clock.
"""
from __future__ import annotations

from acp.approval import ApprovalPolicy
from policies.approval_policy_v1 import APPROVAL_POLICY_V1

__all__ = ["DOGFOOD_TENANT", "policy_config_v1", "load_policy_v1"]

# The internal dogfood tenant this v1 policy is written for (the flip's target; see CLAUDE.md
# "internal tenant only"). Documentation of intent — the policy itself is tenant-agnostic (.md §5).
DOGFOOD_TENANT = "neuraledge"


def policy_config_v1() -> dict:
    """The raw v1 `policy_config` dict (deep copy — callers can't mutate the shared artifact).

    Feed directly to `build_approval(policy_config_v1())` — it does `ApprovalPolicy(**config)`."""
    src = APPROVAL_POLICY_V1
    return {
        "default_mode": src["default_mode"],
        "scope_modes": dict(src["scope_modes"]),
        "overrides": dict(src["overrides"]),
        "hard_deny": set(src["hard_deny"]),
    }


def load_policy_v1() -> ApprovalPolicy:
    """Construct the v1 dogfood `ApprovalPolicy` from the artifact.

    Returns an instance `build_approval` accepts as-is (it passes a non-dict `policy_config` straight
    through). Constructing it also validates every mode via `ApprovalPolicy.__post_init__`."""
    return ApprovalPolicy(**policy_config_v1())
