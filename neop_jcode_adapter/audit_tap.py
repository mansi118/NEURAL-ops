"""AuditTap — every palace op + the session transcript → durable audit (plan §3.6 / task T4).

Target: NATS subject → ClickHouse (nc-audit). Pre-S0 fallback: append-only audit/*.jsonl per seat
(palace_mcp_shim already emits the jsonl rows when NEOP_AUDIT_DIR is set — this module promotes that
to NATS/ClickHouse once the substrate lands). 100% palace-op audit coverage is a hard acceptance bar
(§5); no silent tool surfaces (§6).
"""
from __future__ import annotations


class AuditTap:
    def emit(self, event: dict) -> None:
        raise NotImplementedError("T4 — NATS/ClickHouse sink (jsonl fallback lives in palace_mcp_shim)")

    def export_transcript(self, seat, transcript_ref: str) -> None:
        raise NotImplementedError("T4 — on session end")
