"""EventBridge — NEop lifecycle + significant events → NATS (plan §3.6 / task T4).

Publishes started/stopped/crashed/promoted (and significant events) for the dashboard and other
NEops. Pre-S0 fallback: local log; flip to NATS when it lands.
"""
from __future__ import annotations


class EventBridge:
    def publish(self, subject: str, event: dict) -> None:
        raise NotImplementedError("T4 — NATS publish (local-log fallback pre-S0)")
