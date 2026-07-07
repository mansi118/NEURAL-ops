# Runtime reconciliation — which repo is the NEop runtime, and does NeuralChat ride our spine?

> Traced 2026-07-07 against the actual repos on disk + git remotes, prompted by "wire UI ↔ backend ↔
> spine exhaustively." Trace-before-build caught a fork: the runtime all the wiring docs target is **not on
> this box**, and a *different* complete runtime **is**. This doc records the ground truth on evidence so it
> can't be re-derived, and so nobody builds the Bars 1–2 wiring against the wrong runtime.

## The three repos (git-remote verified)
| On disk | Git remote | What it actually is |
|---|---|---|
| **NOT present** | `mansi118/pi-neop-runtime` | **THE canonical NEop runtime** (Bars 1–2). `ADR-neop-runtime` DECIDED it 2026-06-30; GAP-1, the B-fwd ADR, and `wiring-map.md` all target `src/brokers/memory.ts`. **Not checked out here** — `find` for `pi-neop*` / `brokers/memory.ts` returns nothing. |
| `Oneshot-hermes/` | `mansi118/one-click-hermes` | A different product (coding-agent CLI + Ink TUI + web). Its `package.json` name `hermes-agent` is a red herring. No palace, no seat, no NEop router. **Unrelated.** |
| `NEOS_NeuralChat/` | `mansi118/Neural-chat-context-vault-` | **The Bar-3 product (nc-web / NeuralChat).** Complete: orchestrator→executor→model loop, Convex palace client, an already-built Matrix appservice adapter, bus NEops (Sales/COS/Axe), proactive engine. A *separate track*, not the Bars 1–2 runtime. |

## Finding 1 — the Bars 1–2 runtime is genuinely not here (the `[ML]` gate is real)
`pi-neop-runtime` is not on this box. So:
- **GAP-1 cannot start.** Its Step Zero is "re-trace `memory.ts:23` before porting into it" — the file isn't on disk. The `/mcp` port (`gap1-palace-mcp-port-spec.md`) is a checklist walk *waiting on the checkout*, not doable now.
- **The B-fwd seam has no destination yet.** `ADR-wire-b-forwarding` decided nc-channels forwards `raw` to the Hermes seat endpoint — but that endpoint lives in `pi-neop-runtime`, which isn't here to trace the seat contract against.
- Correction to an in-session error: I briefly said "the checkout gate may already be satisfied" on seeing Hermes-shaped repos. **That was wrong** — neither on-disk repo is `pi-neop-runtime`. The gate stands.

## Finding 2 — NeuralChat (Bar-3) does NOT ride our live CORTEX-PALACE as-built
NeuralChat's palace client (`src/palace/convexClient.ts`) calls Convex functions **by name** via `ConvexHttpClient` + `CONVEX_SERVICE_TOKEN`. Its FN map (`convexClient.ts:28-40`) is, by its own comment, functions "PALACE **must expose** … Phase 0 lands these" — an *expected* contract. Resolved against our live CORTEX-PALACE (`Mempalace_NEOS/convex/`):

| NeuralChat expects | In CORTEX-PALACE? |
|---|---|
| `ingestion/ingest:ingestExchange` | ✅ exists (`ingestion/ingest.ts:50`) |
| `serving/assembleUserContext:assembleUserContext` | ❌ no such export (palace has `serving/assemble.ts`, different fn) |
| `chat/mutations:writeEvent` | ❌ **`convex/chat/` does not exist** |
| `proposals/propose`, `proposals/consumeToken` | ❌ **`convex/proposals/` does not exist** |
| `userPreferences/queries`, `…/briefingState` | ❌ **`convex/userPreferences/` does not exist** |
| `palace/health:health` | ❌ no matching export |

**1 of 7 targets resolves; three whole namespaces are absent.** NeuralChat would throw `PalaceUnavailable`
(`convexClient.ts:111`) against our spine today. It targets its *own* Phase-0 palace spec
(`NEOS_NeuralChat/docs/phase-0-prereqs/`) that CORTEX-PALACE has **not** implemented. So Bar-3 is not just a
separate runtime — it's **not yet connected to our spine at all**; wiring it would need that Phase-0 Convex
surface built on the palace side. Correctly **out of scope for Bars 1–2**.

## The unifying picture — same spine, two different doors
CORTEX-PALACE (`Mempalace_NEOS` Convex) is the one spine, reachable two ways:
- **Door A — `/mcp`** (`convex/http.ts:47,57`; tools `palace_search`, `palace_remember`, `palace_search_temporal`; `palace_remember` routes through `ingestExchange` internally). Scope-baked, ACL-enforced, `{tool,palaceId,neopId,params}` + `X-Palace-Neop`. **This is the door `pi-neop-runtime` uses via GAP-1.** Live and verified (7/7 this arc).
- **Door B — direct Convex functions** (`ConvexHttpClient` + service token, the `serving/*`/`chat/*`/`proposals/*` Phase-0 contract). **This is the door NeuralChat expects** — and it is **not built** on CORTEX-PALACE (Finding 2).

The runtimes don't share a door. Bars 1–2 go through the **built, live** `/mcp` door (runtime absent). Bar-3
would go through the **unbuilt** direct-function door (runtime present). That asymmetry is the whole reason
"which runtime" forks the wiring.

## Net — where "wire UI ↔ backend ↔ spine" actually stands
- **Spine: READY.** `/mcp` is live, ACL-enforced, ranked-retrieval-capable — the exact contract GAP-1 ports.
- **Runtime (Bars 1–2): ABSENT.** `pi-neop-runtime` must be checked out (`[ML]`) before GAP-1 or the B-fwd
  seam can be built or traced. This is the one gate on the whole Wire-B/Wire-C track.
- **Transport (Wire A): DONE + box-gated** (`nc_channels`, PR #87) — independent of the above.
- **Bar-3 (NeuralChat): SEPARATE + not spine-connected.** Reusable idea (its Matrix adapter proves the Node
  AS pattern), but its palace contract is unbuilt on our side; not part of the Bars 1–2 wiring.

**The single unblock:** check out `mansi118/pi-neop-runtime` onto this box. Then — spine ready, contract
specced (`gap1-palace-mcp-port-spec.md`), seam decided (`ADR-wire-b-forwarding`) — GAP-1 is a transcription +
a live proof, and the B-fwd seam is a small authenticated forward. Until then, the Bars 1–2 runtime wiring is
gated, and building against NeuralChat's contract would be building against a door that isn't open on either side.
