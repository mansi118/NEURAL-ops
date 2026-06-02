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
import os, json, urllib.request

__all__ = ["MemPalaceError", "retrieve", "write"]


class MemPalaceError(RuntimeError):
    pass


def _need(key: str) -> str:
    v = os.environ.get(key)
    if not v:
        raise MemPalaceError(f"{key} not set — required for live MemPalace calls")
    return v


def _post(tool: str, palace_id: str, neop_id: str, params: dict) -> dict:
    base = _need("CONVEX_SITE_URL").rstrip("/")
    _need("AWS_BEARER_TOKEN_BEDROCK")  # embeddings gate (server-side); presence-checked here
    body = json.dumps({"tool": tool, "palaceId": palace_id, "neopId": neop_id, "params": params}).encode()
    req = urllib.request.Request(
        f"{base}/mcp", data=body,
        headers={"Content-Type": "application/json", "X-Palace-Neop": neop_id},
    )
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (trusted internal endpoint)
        return json.loads(r.read().decode())


def retrieve(tenant, seat, query, k=5, wing=None, category=None, similarity_floor=0.35):
    """palace_search -> {chunks, provenance}. Single-vector + graph boost (no RRF in live code)."""
    params = {"query": query, "limit": k, "similarityFloor": similarity_floor}
    if wing:
        params["wingFilter"] = wing
    if category:
        params["categoryFilter"] = category
    resp = _post("palace_search", tenant, seat, params)
    results = resp.get("results", [])
    chunks = [{
        "id": r.get("closetId"), "tenant": tenant, "text": r.get("content"),
        "score": r.get("score"), "category": r.get("category"), "wing": r.get("wingName"),
        "created_at": r.get("createdAt"), "source_adapter": r.get("sourceAdapter"),
        "confidence": r.get("confidence"),
    } for r in results]
    prov = [{
        "id": r.get("closetId"), "source_adapter": r.get("sourceAdapter"),
        "created_at": r.get("createdAt"),
    } for r in results]
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
