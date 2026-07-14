"""Governance factory (Track 1) — turn approval-policy-v1 ON as a CONFIG FLIP, not a code edit.

Every piece already exists and is tested in isolation: `acp.approval_policy_v1.policy_config_v1` (the v1
dogfood policy), `runtime.approval_gate.build_approval` (the broker builder, with a REPORT_ONLY governance
mode and a byte-identical OFF path), and `acp.approval_mode` (the report-only evaluator + flip_readiness).
This module is the missing SEAM that reads the environment and composes them into the `approval=` broker
`core.dispatch` consumes — so a tenant enables governance by setting env, never by editing code.

THREE POSTURES, gated so nothing turns on by accident:
  - OFF (default): return None. `dispatch(approval=None)` is byte-identical to today — governance inert.
  - REPORT_ONLY: run the real policy, RECORD what it WOULD do, but let every action PROCEED. This is the
    observe-before-flip window; `broker.readiness()` (flip_readiness) measures the blast radius.
  - ENFORCE: the real gate (allow/await/deny). GATED behind an explicit ack — you cannot flip straight to
    blocking live actions; you must have observed in report-only first and consciously set the ack. This
    encodes "the enforce flip stays gated" in CODE, not just in discipline.

GRANTOR is required whenever governance is on and is NEVER defaulted — a baked grantor is an asserted
identity, exactly what server-derived-requester eliminated everywhere else (see build_approval's docstring).

Pure + offline: no core.py import, no network at construction (the ConvexSnapshotStore only touches the
network on a live save/load, credential-gated). Run: python3 tests/test_governance.py
"""
from __future__ import annotations

import os

from runtime.approval_gate import build_approval, ENFORCE, REPORT_ONLY
from acp.approval_policy_v1 import policy_config_v1

GOV_OFF = "off"
GOV_REPORT_ONLY = "report_only"
GOV_ENFORCE = "enforce"
_OFF_ALIASES = frozenset({"", GOV_OFF, "false", "0", "no", "none"})

__all__ = ["GOV_OFF", "GOV_REPORT_ONLY", "GOV_ENFORCE", "approval_from_env"]


def approval_from_env(env=None):
    """Build the tenant's ApprovalBroker from the environment, or None when governance is OFF.

    Env:
      NEOS_GOVERNANCE            off | report_only | enforce   (default off)
      NEOS_GOVERNANCE_GRANTOR    the granting authority recorded on grants (REQUIRED when on; never baked)
      NEOS_GOVERNANCE_ENFORCE_ACK  must be "yes" to permit NEOS_GOVERNANCE=enforce (the gated flip)
      NEOS_GOVERNANCE_STORE      unit | integration            (default unit)
      PALACE_ID                  required when STORE=integration (per-tenant ConvexSnapshotStore)
    """
    env = env if env is not None else os.environ
    setting = (env.get("NEOS_GOVERNANCE") or GOV_OFF).strip().lower()
    if setting in _OFF_ALIASES:
        return None  # governance disabled — dispatch(approval=None) is byte-identical to today

    if setting not in (GOV_REPORT_ONLY, GOV_ENFORCE):
        raise ValueError(
            f"NEOS_GOVERNANCE must be one of off|report_only|enforce — got {setting!r}")

    grantor = (env.get("NEOS_GOVERNANCE_GRANTOR") or "").strip()
    if not grantor:
        raise ValueError(
            "NEOS_GOVERNANCE is on but NEOS_GOVERNANCE_GRANTOR is blank. The grantor is the granting "
            "authority recorded on every grant; it must be set explicitly and never baked (a hardcoded "
            "grantor is an asserted identity).")

    governance = ENFORCE if setting == GOV_ENFORCE else REPORT_ONLY
    # The ENFORCE flip is GATED: report_only can never silently become enforce. Blocking live actions is a
    # conscious, observed-first step — require an explicit ack, the same posture as the seat's T9 gate.
    if governance == ENFORCE and (env.get("NEOS_GOVERNANCE_ENFORCE_ACK") or "").strip().lower() != "yes":
        raise RuntimeError(
            "REFUSING to enforce governance: NEOS_GOVERNANCE=enforce blocks live actions (deny/await). "
            "Observe in report_only first (broker.readiness()), then set NEOS_GOVERNANCE_ENFORCE_ACK=yes "
            "to consciously flip. (Track 1 governance flip — gated.)")

    store_mode = (env.get("NEOS_GOVERNANCE_STORE") or "unit").strip().lower()
    if store_mode not in ("unit", "integration"):
        raise ValueError(f"NEOS_GOVERNANCE_STORE must be unit|integration — got {store_mode!r}")
    palace_id = (env.get("PALACE_ID") or "").strip() or None
    if store_mode == "integration" and not palace_id:
        raise ValueError(
            "NEOS_GOVERNANCE_STORE=integration requires PALACE_ID (per-tenant ConvexSnapshotStore)")

    return build_approval(
        policy_config_v1(),
        mode=store_mode,
        palace_id=palace_id,
        grantor=grantor,
        governance=governance,
    )
