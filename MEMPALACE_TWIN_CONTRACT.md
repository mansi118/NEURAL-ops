# Mempalace_NEOS — twin server contract (Phase B)

The NEOS twin client (`runtime/memory.py`) and the server handlers are **both implemented**
(server side staged in the `Mempalace_NEOS` clone, NOT yet pushed). A twin is *addressed*, not
searched: one record per `(palaceId, neopId)` in a dedicated **`twins` table**, fetched/written
by address — never embedded, never vector-indexed, never returned by `palace_search`.

> **Design correction (trace-driven):** the earlier draft stored the twin "as a closet" keyed
> `twin::<seat>`. Reading the real schema showed `closets` are embedded, searchable, append-only
> memory units in the room→wing hierarchy — exactly what a twin must NOT be. Corrected to a
> dedicated `twins` table + `palace_get_twin`/`palace_put_twin`. (Tool names changed from
> `palace_get_closet`/`palace_put_closet`.)

> Cross-repo. Staged in `mansi118/Mempalace_NEOS`, **confirm before pushing** (outward-facing) and
> before `convex deploy`. Until deployed, the client's live calls stay credential-gated and refuse
> (proven by `tests/test_memory_twin.py::test_live_path_is_credential_gated`).

## MCP envelope (all tools)
The `/mcp` dispatcher wraps every handler result: `{ "status": "ok", "data": <result> }` on
success, `{ "status": "error", "error": "<msg>" }` on failure. The client's `_post` unwraps
`data` and raises `MemPalaceError` on `error`. `neopId` (= seat) rides the envelope, so the twin
tools need no id param. `(palaceId, neopId)` = `(tenant, seat)`.

## Server pieces (staged in the clone)
- `convex/schema.ts` — `twins` table: `{palaceId, neopId, doc, version, maturity, updatedAt}`,
  index `by_palace_neop`. `doc` = serialized twin JSON (broker owns the schema).
- `convex/palace/twins.ts` — `getTwin` query + `putTwin` mutation.
- `convex/http.ts` — `palace_get_twin` / `palace_put_twin` cases in the dispatch switch.
- `convex/access/enforce.ts` — `palace_get_twin → recall`, `palace_put_twin → remember`.

## Tool 1 — `palace_get_twin` (read-by-address)
    { "tool": "palace_get_twin", "palaceId": "<tenant>", "neopId": "<seat>", "params": {} }

Handler returns (becomes `data`):

    { "twin": { ...twin object... }, "version": N, "maturity": "...", "updatedAt": ms }
    # OR  { "twin": null }   when no twin exists for that seat -> client returns None

## Tool 2 — `palace_put_twin` (blind upsert, latest wins)
Upsert by `(palaceId, neopId)` — one row per seat, latest wins. **NO server-side version check**
(the broker already enforced stale-base; see invariants). Request:

    { "tool": "palace_put_twin", "palaceId": "<tenant>", "neopId": "<seat>",
      "params": { "doc": "<JSON string of twin, sort_keys>", "version": N, "maturity": "..." } }

Handler returns (becomes `data`):

    { "status": "ok", "twinId": "<convex id>", "version": N, "upsert": "insert"|"update" }

## Invariants the server must hold
- **Version ownership = the BROKER, singly.** Versioning + stale-base rejection are enforced
  client-side in `MemoryBroker.put_twin` (`base_version` optimistic-concurrency check → rejects
  `stale_base_version`). The server does NOT version-check — it is a dumb durable store. One
  owner by design: no server-side compare-and-set, so no double-gate or two-checker race.
- **Upsert, not append**: `put` twice for the same `(palaceId, neopId)` ⇒ one row, latest wins.
  ⚠️ **"latest wins" is a blind upsert, not a CAS.** It is correct ONLY under **single-writer
  per twin** — which holds today (the Twin Curator writes one pass per cadence). If concurrent
  writers to the same twin are ever introduced, two brokers can both pass their stale-base check
  (both read vN) and the later `put` silently clobbers the earlier vN+1. Closing that needs a
  server-side conditional upsert (write iff stored version == base_version) — move the gate
  server-side then, do NOT split it across both.
  **The trigger is an EVENT, not a date:** today the Twin Curator is the sole twin writer. The
  assumption breaks the moment (a) the automation flywheel (C2) goes from spec-only to auto-spawn,
  or (b) any NEop starts writing twin deltas in parallel — broker-side CAS can't see writes it
  didn't originate. Keep the flywheel human-gated and single-writer holds. Watch for that event.
- **Tenant isolation**: `palaceId` scopes the closet; seat A in tenant X never reads tenant Y.
- **`twin::` excluded from `palace_search`** so twins never leak into retrieval grounding.

## Verification (joint live session, when creds land)
With `CONVEX_DEPLOYMENT_URL` set against a **scratch seat** (no prod writes):
1. `put_twin(tenant, scratch_seat, twin_v0)` → `status: ok`
2. `get_twin(tenant, scratch_seat)` → returns `twin_v0` (round-trip)
3. `put_twin` a v1 → `get_twin` returns v1 (upsert, not a second row)
4. `get_twin(tenant, "never-seeded")` → `None`

Runs alongside the `palace_search` read smoke (A2) — same Convex connection, one session.
