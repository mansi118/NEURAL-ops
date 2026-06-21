"""Best-effort external-denial emit — record an OUT-OF-Convex denial in the UNIFIED audit so
`denialsByLayer` counts every layer, not just `convex_sot` (native) + the bridge's `falkordb`.

Mirrors the FalkorDB bridge's `_emit_external_denial` (services/graphiti_bridge.py), in the NEURAL-ops
runtime, for the **broker** layer (a client-side scope refusal). Credential-gated
(`CONVEX_DENIAL_SINK_URL` + the shared `PALACE_BRIDGE_API_KEY`) + offline-safe: ANY failure is
swallowed — a denial is already being returned to the caller, so the audit emit must never block,
delay, or raise. Posts to the least-privilege `/external-denial` sink (Mempalace httpAction).
"""
from __future__ import annotations

import json
import os
import urllib.request

__all__ = ["emit_external_denial", "emit_edge_denial"]


def emit_external_denial(palace_id, layer, *, neop_id=None, op=None, reason="", extra=None):
    """Fire-and-forget. No-op unless the sink URL + shared key + a non-blank palace_id are all present
    (an edge denial with no resolved palace cannot be keyed — that path is intentionally not emitted here)."""
    sink = (os.environ.get("CONVEX_DENIAL_SINK_URL") or "").rstrip("/")
    key = os.environ.get("PALACE_BRIDGE_API_KEY") or ""
    if not sink or not key or not (isinstance(palace_id, str) and palace_id.strip()):
        return
    try:
        # OMIT None keys — the sink's recordExternalDenial uses v.optional(v.string()), which accepts
        # absent but REJECTS null. (op must also be a valid audit enum if sent, so callers pass it rarely.)
        payload = {
            "palaceId": palace_id,
            "deniedAtLayer": layer,
            "neopId": (neop_id or "").strip() or "unknown",
            "reason": reason,
        }
        if op:
            payload["op"] = op
        if extra:
            payload["extra"] = json.dumps(extra, sort_keys=True)
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{sink}/external-denial", data=body,
            headers={"Content-Type": "application/json", "X-Palace-Key": key},
        )
        urllib.request.urlopen(req, timeout=3).close()  # noqa: S310 (trusted internal sink)
    except Exception:
        pass  # best-effort: the audit emit must never break the denial path


def emit_edge_denial(rejection, *, resolve_palace_id):
    """Route an EDGE denial to the unified audit — the missing 4th layer (closes #12). The edge lacks
    a palaceId at rejection time (it fails before resolving the tenant NAME), so we resolve it here via
    the injected `resolve_palace_id(tenant_name) -> palaceId | None` (e.g. palace/queries:getPalaceByClient).
    Best-effort + offline-safe: no-op if the tenant is absent or unresolvable. Use as the `on_reject`
    seam of acp.edge_auth.resolve_edge_identity."""
    audit = getattr(rejection, "audit", rejection) or {}
    tenant = audit.get("tenant")
    if not (isinstance(tenant, str) and tenant.strip()):
        return
    try:
        palace_id = resolve_palace_id(tenant)
    except Exception:
        palace_id = None
    if not palace_id:
        return
    emit_external_denial(palace_id, "edge", neop_id=audit.get("claimed"),
                         reason=f"edge: {audit.get('reason')}")
