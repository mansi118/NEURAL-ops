# Matrix UI ⟷ backend ⟷ spine — the end-to-end wiring map

> Ultrathink, 2026-07-07. "Connect the Matrix UI and our backend and spine altogether" is not ONE
> connection — it is **three independent wires**, each solved in a different place, gated on a different
> thing. Conflating them is what made #84 look like "the Bar-1 task" when it is really a Bar-2 concern.
> This doc is the single mental model: what each wire is, where it lives, and its honest state.

## The full path (Bar-2 target — the whole system lit up)
```
 Element (Matrix client, your phone/desktop)
   │  m.room.message  (user types in a room)
   ▼
 Synapse  @ matrix.neuraledge.in   ── EC2, DEFAULT VPC 172.31, public 443/8448, server_name neuraledge.in
   │  PUT /_matrix/app/v1/transactions/{txn}   (Bearer hs_token)      ┐
   ▼                                                                   │  WIRE A — Matrix transport
 nc-channels  (the AS bridge)  ── verify_hs_token → dedup → raw       │  (nc_channels/service.py)
   │  orchestrator.handle(raw, mode="live")                           ┘
   ▼                                                                   ┐
 runtime dispatch  ── core.py RAISES on live → must be Hermes (M1b)    │  WIRE B — the runtime
   │  memory broker: palace_search / palace_remember                  ┘
   ▼                                                                   ┐
 CORTEX-PALACE /mcp  @ convex.neos-dogfood.local:3211  ── SPINE VPC    │  WIRE C — the memory spine
   │  Titan embed → ranked recall ; LLM = OpenRouter (egress)          │  (GAP-1 + cross-VPC reach)
   ▼  result["stream"]                                                 ┘
 nc-channels.reply_send → _cs_api_call
   │  PUT /_matrix/client/v3/rooms/{room}/send/m.room.message/{txn}  (Bearer as_token)
   ▼
 Synapse ──► Element   (the NEop's reply appears in the room)
```

## Why THREE wires, not one — and why that ordering matters
Each wire fails independently and is proven independently. You cannot "connect it all at once"; you light
them up in sequence, and each has a different owner and a different proof.

### WIRE A — Matrix transport  (Element ↔ Synapse ↔ nc-channels)
- **What:** the AS handshake. Receive `PUT /transactions` (hs_token), reply via CS-API (as_token).
- **Where it lives:** `nc_channels/service.py` — `serve()` + `_cs_api_call()`. **Code-complete (PR #87).**
- **Needs the spine? NO. Needs a live NEop? NO.** With `reflect=True` it hardcodes `echo ⟳ <text>`.
- **State:** implemented; request construction unit-proven (47/47). **The live round-trip is box-gated**
  — proven ONCE on the matrix box against real Synapse (never mocked, D1). **This is Bar 1a.**
- **Deploy for the proof:** co-locate nc-channels ON the matrix box → Synapse hop = `localhost:8008`,
  inbound = `localhost:8010`. **No ALB, no cross-VPC, no palace.** (Placement doc #84 is NOT this — see C.)

### WIRE B — the runtime  (nc-channels ↔ a NEop that actually thinks)
- **What:** turn `raw` into a real reply. `orchestrator.handle(mode="live") → runtime dispatch`.
- **The gate (the load-bearing finding, #86):** `runtime/core.py` `ModelBroker` **RAISES on live**
  (`core.py:171/195`). The Python `core.py` is the UNIT reference only. The decided live runtime is
  **Hermes** (`pi-neop-runtime`, Node/TS — ADR-neop-runtime). So a *real* echo NEop is gated on standing
  up Hermes (**M1b**), NOT on the bridge. Bar 1a exists precisely to prove Wire A without waiting on this.
- **⚠️ OPEN ARCHITECTURAL DECISION (surface, don't paper over):** today `service.py` calls
  `orchestrator.handle` **in-process (Python)**. The live runtime is **Hermes (Node)**. Those don't
  compose in-process. So Wire B forces a choice:
    - **(B-fwd) nc-channels stays a thin Python transport** and *forwards* `raw` to Hermes over
      HTTP/queue (Hermes serves the seat, owns dispatch + memory). nc-channels never runs the runtime.
    - **(B-port) the bridge logic moves into Hermes** and the Python nc-channels is retired after Bar 1a.
  **Recommendation: B-fwd.** It keeps the proven Python AS transport (Wire A) as-is, makes the Python↔Node
  seam an explicit network call (testable, jailable), and matches "jcode/Hermes is configured, not forked."
  Under B-fwd, `reflect=False` becomes "POST raw to the Hermes seat endpoint, stream the reply back" —
  a small, well-defined change to `serve()`, not a rewrite. **Decide this before building Bar 1b.**
- **State:** BLOCKED on M1b (Hermes checkout + GAP-1/GAP-2). This is the gap between Bar 1a and Bar 1b.

### WIRE C — the memory spine  (runtime ↔ palace /mcp)
- **What:** the NEop recalls/persists memory. `memory broker → /mcp` (palace_search/remember).
- **Two sub-problems, both real:**
  1. **The broker (GAP-1):** port the `/mcp` contract (scope baked from env, fail-closed, the real
     `{"tool","palaceId","neopId","params"}` body — see CLAUDE.md correction #2) into
     `pi-neop-runtime/src/brokers/memory.ts`. Proof = `tools/ranked_retrieval_proof.py` shape.
  2. **The network:** palace is `convex.neos-dogfood.local:3211`, **SPINE VPC 10.40, internal only**.
     Synapse is **default VPC 172.31, public**. nc-channels/runtime must touch **both**. That is the
     real content of placement doc **#84 → Option B**: run nc-channels/runtime **in the spine VPC**
     (palace hop = internal, trivial) and give Synapse an **inbound** path to it via a **public
     token-gated HTTPS ALB** (`verify_hs_token` bounds the exposure). Reply hop = plain egress to public
     Synapse. No VPC peering.
- **State:** BLOCKED on M1b (GAP-1) AND the #84 infra (ALB + re-targeted `nc-channels.tf`). **This is Bar 2.**

## The relocation that the three-wire split makes explicit
Bar 1a proves Wire A **co-located on the matrix box** (default VPC, localhost Synapse). Bar 2 runs the
SAME `serve()`/`_cs_api_call` code **in the spine VPC** (behind the #84 ALB, palace reachable). So:
- The **code is location-independent** — `hs_base_url` is a constructor param; nothing in Wire A is
  pinned to the matrix box. Bar 1a de-risks the exact transport code Bar 2 redeploys. Not throwaway.
- But the **deployment moves** (matrix box → spine VPC) when the NEop starts needing the palace. That's a
  redeploy + the #84 inbound ALB, not a config flip. Plan for a move, not a toggle.

## Honest per-wire state (use this, not an optimistic headline)
| Wire | What connects | Lives in | State | Gated on |
|------|---------------|----------|-------|----------|
| A — transport | Element↔Synapse↔nc-channels | `service.py` serve/_cs_api_call | **code-complete (#87)**, box-proof pending | a box session on the matrix box |
| B — runtime | nc-channels↔thinking NEop | Hermes `pi-neop-runtime` | **blocked** | M1b + the B-fwd/B-port decision |
| C — memory | runtime↔palace /mcp | `memory.ts` + spine-VPC deploy | **blocked** | GAP-1 + #84 ALB/`nc-channels.tf` |

## What "connect it all" concretely means, in order
1. **Bar 1a (now):** box-prove Wire A. Element → `echo ⟳ …` → Element, co-located, localhost. Proves the
   transport is real. **The only thing between here and a green is a hands-on-the-box session.**
2. **Decide B-fwd vs B-port** (recommend B-fwd) — the one open architectural call. Cheap to decide, gates B.
3. **M1b:** check out `pi-neop-runtime`, GAP-1 (`memory.ts` /mcp broker), GAP-2 (Node egress jail). Lights
   Wire B (echo runs live = **Bar 1b**) and makes Wire C reachable.
4. **Bar 2:** #84 infra (spine-VPC nc-channels + public ALB + re-targeted `nc-channels.tf`), prove ranked
   recall (`ranked_retrieval_proof.py`), memory-backed reply in Element.
5. Bars 1a→1b→2 lit in that order = the Matrix UI, the backend, and the spine connected altogether —
   honestly, one wire at a time, each proven for what it proves.
