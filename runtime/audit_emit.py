"""Best-effort external-denial emit — record an OUT-OF-Convex denial in the UNIFIED audit so
`denialsByLayer` counts every layer, not just `convex_sot` (native) + the bridge's `falkordb`.

Mirrors the FalkorDB bridge's `_emit_external_denial`, in the NEURAL-ops runtime, for the **broker**
and **edge** layers. Three properties the denial path requires:
  1. credential-gated  — no-op unless `CONVEX_DENIAL_SINK_URL` + the shared `PALACE_BRIDGE_API_KEY` are set;
  2. best-effort       — any failure is swallowed; the emit never raises;
  3. OUT-OF-BAND       — the network work (palace resolve + the POST) runs on a daemon thread, so an emit
                         NEVER blocks or shifts the timing of the denial that triggered it. This matters
                         on the edge security boundary: a synchronous resolve would leak, via response
                         latency, whether a claimed tenant resolves to a real palace. Fire-and-forget
                         removes that side-channel — the rejection returns at constant time either way.

Tests set `audit_emit._SYNC = True` to run the dispatch inline + deterministically.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request

__all__ = ["emit_external_denial", "emit_edge_denial"]

_SYNC = False   # tests flip to True for inline, deterministic emits


def _swallow(fn):
    try:
        fn()
    except Exception:
        pass


def _dispatch(fn):
    """Run fn OFF the caller's critical path (daemon thread), swallowing all errors — so the emit can
    never block, delay, or affect the timing of the denial that triggered it. Inline when _SYNC."""
    if _SYNC:
        _swallow(fn)
        return
    try:
        threading.Thread(target=lambda: _swallow(fn), daemon=True).start()
    except Exception:
        pass


def _creds():
    sink = (os.environ.get("CONVEX_DENIAL_SINK_URL") or "").rstrip("/")
    key = os.environ.get("PALACE_BRIDGE_API_KEY") or ""
    return (sink, key) if (sink and key) else (None, None)


def _post(sink, key, palace_id, layer, *, neop_id=None, op=None, reason="", extra=None):
    """The actual POST to the least-privilege /external-denial sink. OMITS None keys — the sink's
    recordExternalDenial uses v.optional(v.string()), which accepts absent but REJECTS null."""
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
    req = urllib.request.Request(
        f"{sink}/external-denial", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Palace-Key": key},
    )
    urllib.request.urlopen(req, timeout=3).close()  # noqa: S310 (trusted internal sink)


def emit_external_denial(palace_id, layer, *, neop_id=None, op=None, reason="", extra=None):
    """Fire-and-forget. No-op unless creds + a non-blank palace_id are present (an edge denial with no
    resolved palace cannot be keyed). The POST runs off the critical path."""
    sink, key = _creds()
    if not sink or not (isinstance(palace_id, str) and palace_id.strip()):
        return
    _dispatch(lambda: _post(sink, key, palace_id, layer, neop_id=neop_id, op=op, reason=reason, extra=extra))


def emit_edge_denial(rejection, *, resolve_palace_id):
    """Route an EDGE denial to the unified audit — the 4th layer (closes #12). The edge lacks a palaceId
    at rejection time, so the tenant NAME is resolved → palaceId via the injected resolver. BOTH the
    resolve AND the POST run off the critical path (daemon thread), so the rejection's timing is constant
    regardless of whether the palace resolved — no tenant-existence latency oracle. Best-effort + no-op
    if the tenant is absent or unresolvable. Use as the `on_reject` seam of resolve_edge_identity."""
    audit = getattr(rejection, "audit", rejection) or {}
    tenant = audit.get("tenant")
    if not (isinstance(tenant, str) and tenant.strip()):
        return
    sink, key = _creds()
    if not sink:
        return

    def work():
        palace_id = resolve_palace_id(tenant)
        if not palace_id:
            return
        _post(sink, key, palace_id, "edge", neop_id=audit.get("claimed"),
              reason=f"edge: {audit.get('reason')}")

    _dispatch(work)   # resolve + POST both off the critical path → constant-time rejection
