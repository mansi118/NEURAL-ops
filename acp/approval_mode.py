"""Approval governance MODE — report-only vs enforce (Phase-A governance flip).

The plan turns approval-policy-v1 on in REPORT-ONLY first: run the real policy decision, RECORD what
it WOULD do, but let the action PROCEED — so a tenant can measure the blast radius (how many actions
would be denied / would need approval) BEFORE flipping to ENFORCE. That de-risks the flip: you never
discover the policy blocks legitimate day-to-day work by having it block live.

Pure layer over `acp.approval` — `decide`/`resolve_grant`/`audit_record` are untouched, so ENFORCE
behaviour is exactly today's. No core.py import, no network, no wall-clock (`when` stamped at the sink).
"""
from __future__ import annotations

from acp.approval import Action, ApprovalPolicy, decide, audit_record, ALLOW, DENY, AWAIT  # noqa: F401

ENFORCE = "enforce"
REPORT_ONLY = "report_only"
MODES = frozenset({ENFORCE, REPORT_ONLY})

__all__ = ["ENFORCE", "REPORT_ONLY", "MODES", "evaluate", "flip_readiness"]


def evaluate(action, policy, *, mode=ENFORCE):
    """→ (effective_decision, audit).

    ENFORCE: effective = the real policy decision (allow / deny / await); audit tagged enforced=True.
    REPORT_ONLY: the policy decision is recorded as `would`, but effective is ALWAYS ALLOW — nothing is
    blocked while observing. The audit carries enforced=False + `would` so the flip-readiness summary
    can count what the policy WOULD have done on live traffic.
    """
    if mode not in MODES:
        raise ValueError(f"unknown governance mode {mode!r} — one of {sorted(MODES)}")
    would, reason = decide(action, policy)
    if mode == ENFORCE:
        audit = audit_record(action, would, reason)
        audit.update({"mode": ENFORCE, "enforced": True})
        return would, audit
    audit = audit_record(action, ALLOW, f"report_only(would={would}: {reason})")
    audit.update({"mode": REPORT_ONLY, "enforced": False, "would": would})
    return ALLOW, audit


def flip_readiness(audits):
    """Summarize a window of REPORT_ONLY audits → how disruptive ENFORCE would be. Counts what WOULD
    have happened; `block_rate` = (would_deny + would_await) / total. A low, stable block_rate over a
    real traffic window is the signal that flipping to ENFORCE won't wall off legitimate work. Non
    report-only audits are ignored, so a mixed stream is safe to pass in."""
    would = {ALLOW: 0, DENY: 0, AWAIT: 0}
    total = 0
    for a in audits:
        if not isinstance(a, dict) or a.get("mode") != REPORT_ONLY:
            continue
        total += 1
        w = a.get("would", ALLOW)
        would[w] = would.get(w, 0) + 1
    blocked = would[DENY] + would[AWAIT]
    return {
        "total": total,
        "would_allow": would[ALLOW],
        "would_deny": would[DENY],
        "would_await": would[AWAIT],
        "block_rate": round(blocked / total, 3) if total else None,
    }
