"""MemoryPromoter — session-end promotion of jcode's ephemeral local graph → palace (plan §3.7 / T6).

The palace stays SoT; jcode's local memory graph is a per-seat working cache. On session end, promote
durable items via palace_remember (through the shim, so scope is baked + audited). Ephemeral chatter
is NOT promoted. Mirrors the Vault Promoter pattern. Goes through palace_mcp_shim — never a direct
palace call — so promotion inherits the same scope-lock + audit as live ops.
"""
from __future__ import annotations


class MemoryPromoter:
    def promote(self, seat, local_graph) -> int:
        """Return the count of items promoted. Durable-only; scoped via the shim."""
        raise NotImplementedError("T6 — pending jcode local-graph export format from the clone")
