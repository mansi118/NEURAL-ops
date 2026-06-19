"""MemoryPromoter — session-end promotion of jcode's local graph → palace (plan §3.7 / T6).

CORRECTION (traced from jcode@master): jcode's memory graph is DURABLE, not ephemeral — it persists at
``$JCODE_HOME/memory/`` with scopes Global/Project/Session (only Session is transient). Export path:
``jcode memory export <out.json> --scope project|global|all`` (or the in-agent ``memory`` tool). So
promotion = export the durable (Global/Project) items, then write each into the palace via
``palace_remember`` THROUGH the shim (scope baked + audited) — never a direct palace call. Session-scope
chatter is NOT promoted. The palace stays SoT; the jcode graph is the per-seat working cache. Mirrors
the Vault Promoter pattern.
"""
from __future__ import annotations


class MemoryPromoter:
    def promote(self, seat, local_graph) -> int:
        """Return the count of items promoted. Durable-only; scoped via the shim."""
        raise NotImplementedError("T6 — pending jcode local-graph export format from the clone")
