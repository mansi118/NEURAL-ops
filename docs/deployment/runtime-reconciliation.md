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

---

## POST-CHECKOUT UPDATE — cloned `pi-neop-runtime`; GAP-1/GAP-2 are BUILT, and the seam-shape fork appears
Cloned `mansi118/pi-neop-runtime` (2026-07-07) and ran GAP-1 Step Zero. The 2026-06-30 ADR snapshot is
**stale by two commits** — `git log`: `#1 feat: Hermes live execution path — /mcp memory (GAP-1) + D2 +
seat-serve` and `#2 feat(jail): GAP-2 hardened Node runtime image`.

**GAP-1 is already ported (well):**
- `src/brokers/palaceClient.ts` is a faithful 1:1 TS port of `palace_mcp_shim.py` — scope baked from env,
  fail-closed on blank + reserved (`_admin`/`_system`) scope, spoof-key rejection, allowlist
  (`palace_search`/`palace_remember`, `palace_get_closet` gated), Ed25519 hook, the real
  `{tool,palaceId,neopId,params}` + `X-Palace-Neop` envelope, `ok = 200 && status=="ok"`, injectable transport.
- `src/brokers/memory.ts` wires it live: `retrieve→palace_search`, `write→palace_remember`, **throws on
  `!ok`** (never returns empty-on-error), empty=`[]` left for the proof to judge. The `memory.ts:23` throw
  the spec targets is **gone** — GAP-1 Part 1 (transcription) + Part 2 (fail-closed) are **DONE in code.**
- ⇒ **GAP-1's remaining work is only Part 3** — the live ranked-retrieval proof (seed BLUEFERN, near+oblique,
  rank-1 ≥ ABS_MIN, cross-seat isolation). Box-gated, needs a seeded seat + live palace. Not a build.
- **GAP-2** (Node egress-jail image) is built (commit #2); box-proof pending. Same shape: built, not proven.

**The seat entrypoint — and the fork it exposes:**
- `src/serve.ts` `serveSeat(neopPath, SeatTask, mode) → dispatch → RunResult`. It is an **in-process
  function**, invoked **only via the CLI** `nrt serve`, which **hard-refuses `--mode live` unless
  `--i-understand-this-is-T9 yes`** is passed (`cli.ts:218-226`). **There is no HTTP seat server** — the
  only outbound `fetch` is the palace client. The T9 STOP-AND-ASK gate is baked into the runtime itself.
- `RunResult` (`supervisor.ts:29-40`) = `{runId, neop, caseId, terminalState: DONE|FAILED|ESCALATED, plan,
  taskOutcomes[], replansPerformed, trace, error?, acceptanceAllPass}` — a **task-execution result, not a
  chat reply.** The runtime is a plan→execute→verify **task runner**, not a conversational responder.

**⇒ The B-fwd seam is NOT "a small authenticated forward" as the ADR assumed.** It needs THREE things that
don't exist yet, and one product decision:
1. An **HTTP seat wrapper** on the runtime side (accept a forwarded message → `SeatTask` → `serveSeat` →
   map `RunResult` → reply). Building one that runs a live NEop **crosses T9** (CLAUDE.md STOP-AND-ASK + the
   CLI's own hard gate).
2. A **`RunResult` → Matrix-reply rendering** — non-trivial, because a task-run yields outcomes/terminal
   state, not a reply string.
3. The **Python `nc_channels` forward** (`reflect=False`) on the bridge side.
4. **THE DECISION (yours):** does a Matrix message trigger a **full NEop task-run** (plan→execute→verify,
   side-effecting tools, Policy-v1 approvals) or a **lightweight conversational reply**? The runtime is built
   for the former; a chat UX implies the latter. This decides the entire shape of the seam — build it before
   authoring the wrapper.

**Corrected net:** spine READY; runtime memory/jail **BUILT (box-proof pending)**, not unbuilt; the seat is a
**T9-gated task-runner**, not an HTTP chat endpoint. The remaining wiring is the **B-fwd seam** — gated on
(a) the task-run-vs-reply decision and (b) the T9 STOP-AND-ASK before any live NEop runs.
