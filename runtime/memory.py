"""Live MemPalace client (integration-mode memory) — facade over Convex /mcp.

MemPalace is a FACADE: Convex is the system-of-record (vector index + closets),
FalkorDB is an advisory graph (eventually consistent, can be down), and AWS Bedrock
Titan v2 (1024-d, ap-south-1) does embeddings. Access is HTTP:
    POST {CONVEX_SITE_URL}/mcp   tool=palace_search   (retrieve)
    POST {CONVEX_SITE_URL}/mcp   tool=palace_remember (write)

Lazy + credential-gated: nothing here runs in unit mode. Mirrors runtime/aws.py —
the broker's `mode` decides recorded-bundle vs this live path; MemPalace details
never reach the phase machine.

Required env:
    CONVEX_SITE_URL            e.g. https://modest-camel-322.convex.site
    AWS_BEARER_TOKEN_BEDROCK   Bedrock embeddings lease (12h)
tenant -> palaceId (e.g. "neuraledge"); seat -> neopId (e.g. "aria").
"""
from __future__ import annotations
import os, json, urllib.request, urllib.error

__all__ = ["MemPalaceError", "retrieve", "write", "get_twin", "put_twin",
           "twin_put_params", "twin_from_response"]


class MemPalaceError(RuntimeError):
    pass


def _need(key: str) -> str:
    v = os.environ.get(key)
    if not v:
        raise MemPalaceError(f"{key} not set — required for live MemPalace calls")
    return v


def _require_scope(tool: str, palace_id: str, neop_id: str) -> None:
    """Layer-4 (broker) seat-scope guard — DEFENSE IN DEPTH, not the system of record.

    The Convex SoT (Gates A/B) is the authoritative enforcer of per-room seat isolation.
    The broker cannot — and must not — mirror room ownership client-side: that would
    duplicate the SoT and risk staleness. What it CAN guarantee at the call site is
    identity well-formedness: refuse to issue any scoped MemPalace op without an explicit,
    non-blank tenant (palaceId) and seat (neopId). This matters because the server defaults
    a missing neopId to "_admin" (convex/http.ts) — so a blank seat would SILENTLY escalate
    to admin. Failing closed here, tagged denied_at_layer=broker, keeps that off the wire."""
    for label, val in (("tenant/palaceId", palace_id), ("seat/neopId", neop_id)):
        if not isinstance(val, str) or not val.strip():
            raise MemPalaceError(
                f"denied_at_layer=broker: {tool} requires a non-blank {label} (got {val!r}) "
                f"— refusing to call MemPalace with an implicit identity")


def _post(tool: str, palace_id: str, neop_id: str, params: dict) -> dict:
    # Layer-4 defense-in-depth: never put a scoped op on the wire without an explicit
    # tenant+seat (a blank neopId would default to "_admin" server-side — convex/http.ts).
    _require_scope(tool, palace_id, neop_id)
    # Targets Mempalace_NEOS (Convex SoT + Voyage embeddings). Embeddings/Voyage are
    # server-side in Convex, so the client only needs the Convex URL — no embedding key.
    base = (os.environ.get("CONVEX_DEPLOYMENT_URL") or _need("CONVEX_SITE_URL")).rstrip("/")
    body = json.dumps({"tool": tool, "palaceId": palace_id, "neopId": neop_id, "params": params}).encode()
    req = urllib.request.Request(
        f"{base}/mcp", data=body,
        headers={"Content-Type": "application/json", "X-Palace-Neop": neop_id},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (trusted internal endpoint)
            resp = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # The server enforces seat isolation (Gates A/B) and returns 403 on an ACL denial.
        # urlopen raises on any 4xx/5xx, so classify here: surface a denial as a TYPED,
        # layer-attributed broker error instead of an opaque urllib stack trace.
        detail = ""
        try:
            detail = e.read().decode()[:200]
        except Exception:
            pass
        if e.code == 403:
            raise MemPalaceError(f"denied_at_layer=convex_sot: {tool} -> HTTP 403 {detail}") from e
        raise MemPalaceError(f"mempalace_http_error: {tool} -> HTTP {e.code} {detail}") from e
    # Server envelope is {status:"ok", data:<result>} | {status:"error", error}. Unwrap to the
    # result so callers see the handler's return value directly (matches convex/http.ts).
    if isinstance(resp, dict):
        if resp.get("status") == "error":
            raise MemPalaceError(f"{tool} failed: {resp.get('error')}")
        if "data" in resp:
            return resp["data"]
    return resp


def retrieve(tenant, seat, query, k=5, wing=None, category=None, similarity_floor=0.35,
             rrf=True, rrf_k=60):
    """palace_search -> {chunks, provenance} (P-1). Today the backend returns ONE ranked list
    (server-side vector + graph boost); we run it through the RRF primitive (single list =
    identity, so behaviour is unchanged until more channels arrive). The S2 §2.5 four-backend
    fan-out (vector·BM25·graph·recency) lives server-side and is DEFERRED to the live session —
    when present, append each channel's list to `signal_lists` and rrf.fuse_results merges them.
    Contract unchanged; provenance retained per chunk + aligned to fused order."""
    params = {"query": query, "limit": k, "similarityFloor": similarity_floor}
    if wing:
        params["wingFilter"] = wing
    if category:
        params["categoryFilter"] = category
    resp = _post("palace_search", tenant, seat, params)
    vector = [{
        "id": r.get("closetId"), "tenant": tenant, "text": r.get("content"),
        "score": r.get("score"), "category": r.get("category"), "wing": r.get("wingName"),
        "created_at": r.get("createdAt"), "source_adapter": r.get("sourceAdapter"),
        "confidence": r.get("confidence"),
        "provenance": {"id": r.get("closetId"), "source_adapter": r.get("sourceAdapter"),
                       "created_at": r.get("createdAt")},
    } for r in resp.get("results", [])]
    signal_lists = [vector]   # DEFERRED (live session): + bm25, graph multi-hop, recency channels
    if rrf:
        from runtime.rrf import fuse_results
        fused = fuse_results(signal_lists, k=k, rrf_k=rrf_k)
        chunks, prov = fused["chunks"], [p for p in fused["provenance"] if p]
    else:
        chunks = vector[:k]
        prov = [c["provenance"] for c in chunks if c.get("provenance")]
    return {"chunks": chunks, "provenance": prov,
            "confidence": resp.get("confidence"), "reason": resp.get("reason")}


def write(tenant, seat, record):
    """palace_remember -> ack. Idempotent on (sourceAdapter, sourceExternalId)."""
    params = {"content": record.get("content", ""),
              "title": record.get("title"),
              "context": record.get("context", "")}
    resp = _post("palace_remember", tenant, seat, params)
    return {"status": resp.get("status", "ok"),
            "closet_id": resp.get("closetId") or resp.get("closetsCreated"),
            "dedup_key": record.get("provenance", {}).get("source_external_id")}


# --- twin: per-seat structured state, ADDRESSED not searched (Convex SoT) ----------
# A twin is NOT a closet (closets are embedded/searchable memory units). It is one record per
# (tenant=palaceId, seat=neopId) in a dedicated `twins` table, fetched/written by address via
# two server tools the corpus-search path never touches (see MEMPALACE_TWIN_CONTRACT.md):
#     palace_get_twin  {}                          -> read-by-(palaceId,neopId)  (NOT palace_search)
#     palace_put_twin  {doc, version, maturity}    -> blind upsert; latest wins
# The broker (MemoryBroker.put_twin) is the SOLE owner of versioning/stale-base — the server does
# NO version check. Marshalling below is PURE + offline-gradeable; only _post touches the network.


def twin_put_params(twin):
    """palace_put_twin params: the twin serialized as `doc` (broker owns schema) + denormalized
    version/maturity for cheap server-side reads. seat (neopId) rides the _post envelope."""
    return {"doc": json.dumps(twin, sort_keys=True),
            "version": twin.get("version"), "maturity": twin.get("maturity")}


def twin_from_response(resp):
    """get_twin response is {twin: <obj>|null, ...}; return the twin dict or None."""
    t = (resp or {}).get("twin")
    return t if isinstance(t, dict) else None


def get_twin(tenant, seat):
    """Read-by-address -> twin dict | None. Twin is keyed (palaceId, neopId); never searched."""
    return twin_from_response(_post("palace_get_twin", tenant, seat, {}))


def put_twin(tenant, seat, twin):
    """Blind upsert (latest wins). Versioning/stale-base already enforced by MemoryBroker.put_twin."""
    resp = _post("palace_put_twin", tenant, seat, twin_put_params(twin))
    return {"status": (resp or {}).get("status", "ok"), "twin_id": f"{tenant}:{seat}",
            "version": twin.get("version"), "maturity": twin.get("maturity")}
