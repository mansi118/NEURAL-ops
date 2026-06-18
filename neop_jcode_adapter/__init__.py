"""neop_jcode_adapter — run a NEop's inner loop on jcode behind the NEOS runtime contract.

NEOS owns identity, ACL, audit, events, transport. jcode owns only the per-seat agent loop.
jcode is CONFIGURED, never forked. See docs/neop-jcode-adapter-implementation-plan.md and the
repo-root CLAUDE.md (with the 2026-06-18 VERIFIED REALITY corrections).

Build order (plan §4): T0 spike (box-gated) → T1 palace_mcp_shim (done) → T2 ConfigRenderer +
IsolationUnit → T3 SeatSupervisor → T4 AuditTap + EventBridge → T5 SafetyPolicy → T6 MemoryPromoter
→ T7 red-team → (T8 palace_get_closet, optional) → T9/T10 pilots → T11 soak.
"""

from .palace_mcp_shim import PalaceShim, ShimError, ScopeNotConfigured, ToolRejected, ScopeSpoofRejected
from .seat_classes import SeatClass, SEAT_CLASS_PRESETS

__all__ = [
    "PalaceShim",
    "ShimError",
    "ScopeNotConfigured",
    "ToolRejected",
    "ScopeSpoofRejected",
    "SeatClass",
    "SEAT_CLASS_PRESETS",
]
