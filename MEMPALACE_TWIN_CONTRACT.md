# Mempalace_NEOS — twin server contract (Phase B)

The NEOS twin client (`runtime/memory.py`) is wired and offline-green. To run the live twin
smoke it needs two server-side `/mcp` tools in **Mempalace_NEOS** (Convex SoT). They do **not**
exist yet — this is the spec to implement there. A twin is *addressed*, not searched: one record
per `(palaceId, neopId)` fetched/upserted by a deterministic `closetId`, never via `palace_search`.

> Cross-repo. Implement in `mansi118/Mempalace_NEOS`, **confirm before pushing** (outward-facing).
> Until then the client's live calls stay credential-gated and refuse (proven by
> `tests/test_memory_twin.py::test_live_path_is_credential_gated`).

## closetId convention
The client addresses a seat's twin at:

    closetId = "twin::" + neopId        # e.g. "twin::aria"  (TWIN_NS = "twin")

The `twin::` namespace is reserved — a twin closet must never collide with a memory closet and
must be excluded from `palace_search` results (it is structured state, not retrievable context).

## Tool 1 — `palace_get_closet` (read-by-id)
Request body (same envelope as the other tools):

    { "tool": "palace_get_closet", "palaceId": "<tenant>", "neopId": "<seat>",
      "params": { "closetId": "twin::<seat>" } }

Response — the client reads `resp.closet` (falls back to `resp.result`):

    { "closet": { "twin": { ...twin object... } } }     # preferred: structured field
    # OR  { "closet": { "content": "<JSON string of twin>" } }   # accepted: JSON mirror
    # OR  { "closet": null }                              # not found -> client returns None

Either shape works — `twin_from_closet()` prefers the structured `twin` field, else parses
`content` as JSON, else returns `None`. Missing/empty closet ⇒ `None` (a seat with no twin yet).

## Tool 2 — `palace_put_closet` (write-by-id, upsert)
**Upsert by `closetId`** — NOT content-dedup (twins mutate in place; a new version must
overwrite the same row, not create a second closet). Request:

    { "tool": "palace_put_closet", "palaceId": "<tenant>", "neopId": "<seat>",
      "params": { "closetId": "twin::<seat>", "category": "twin",
                  "twin": { ...twin object... },
                  "content": "<JSON string of twin, sort_keys>" } }

Store the structured `twin` (and/or the `content` mirror) at that `closetId`, overwriting any
prior value. Response:

    { "status": "ok", "closetId": "twin::<seat>" }

## Invariants the server must hold
- **Upsert, not append**: `put` twice for the same `(palaceId, neopId)` ⇒ one row, latest wins.
  (Versioning + stale-base rejection are enforced client-side in `MemoryBroker.put_twin`; the
  server is the durable store.)
- **Tenant isolation**: `palaceId` scopes the closet; seat A in tenant X never reads tenant Y.
- **`twin::` excluded from `palace_search`** so twins never leak into retrieval grounding.

## Verification (joint live session, when creds land)
With `CONVEX_DEPLOYMENT_URL` set against a **scratch seat** (no prod writes):
1. `put_twin(tenant, scratch_seat, twin_v0)` → `status: ok`
2. `get_twin(tenant, scratch_seat)` → returns `twin_v0` (round-trip)
3. `put_twin` a v1 → `get_twin` returns v1 (upsert, not a second row)
4. `get_twin(tenant, "never-seeded")` → `None`

Runs alongside the `palace_search` read smoke (A2) — same Convex connection, one session.
