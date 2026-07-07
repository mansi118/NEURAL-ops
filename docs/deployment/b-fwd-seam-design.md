# B-fwd seam — intent-routed design (Matrix message → NEop → reply)

> Design-doc-first (your call), companion to `runtime-reconciliation.md` (#89) and refining
> `ADR-wire-b-forwarding`. The ADR decided *that* nc-channels forwards to Hermes; the post-checkout trace
> falsified its "small forward" assumption. This doc designs the ACTUAL seam given ground truth: the runtime
> is a T9-gated **task runner** (`serveSeat→dispatch→RunResult`), has **GAP-1 memory already wired**, and has
> **no HTTP seat server, no reply path, and no message-intent classifier**. Decision taken: **intent-routed**
> — chit-chat/question → conversational reply; actionable → task-run. **No code until this shape is approved.**

## Ground truth this design is built on (verified 2026-07-07)
- **Spine:** `/mcp` live (`Mempalace_NEOS/convex/http.ts`), ACL-enforced. `palace_search` / `palace_remember`.
- **Runtime memory (GAP-1):** BUILT — `pi-neop-runtime/src/brokers/palaceClient.ts` (1:1 shim port, scope
  baked from env, fail-closed) + `memory.ts` `MemoryBroker` (`retrieve→palace_search`, `write→palace_remember`,
  throws on `!ok`). `assembleContext(text)` returns `{input, twin, stm, retrieval}`.
- **Task path:** `dispatch(neopPath, runCase, mode) → RunResult` (`api.ts:13`) via `SessionSupervisor`
  (plan→execute→verify). `serveSeat` (`serve.ts:47`) wraps it; **CLI-only, hard-gated behind
  `--i-understand-this-is-T9 yes`** (`cli.ts:218-226`). `RunResult` = `{terminalState: DONE|FAILED|ESCALATED,
  taskOutcomes[], plan, trace, acceptanceAllPass, error?}` — outcomes, not a reply string.
- **Model broker:** `ModelBroker` (`model.ts`), provider-aware (OpenRouter primary, D2). Each NEop declares
  `planner`/`executor`/`classifier` models (`schema.ts:39`) — **a classifier slot already exists to reuse.**
- **Missing (this seam must add):** an HTTP seat server; a conversational **reply** path; a **message-intent
  classifier**; the `RunResult`→Matrix-reply rendering; the Python `nc_channels` forward (`reflect=False`).

## The seam, end to end
```
Element → Synapse → nc_channels (Python bridge)                     [Wire A — DONE]
  reflect=False:  POST raw → B-fwd forward (authenticated + scope-baked)   ← Python side (new)
     ▼
pi-neop-runtime  HTTP seat wrapper  POST /seat/turn                  ← NEW on the runtime (design below)
     │  auth: verify bridge; scope (palaceId, neopId) baked from THIS process env, never from the payload
     ▼
  Intent classifier  (ModelBroker.classifier model)                 ← NEW
     ├─ "conversational" ─▶ REPLY path  (NEW):                       ← the actual Bar-2 win
     │        MemoryBroker.assembleContext(text)  →  ModelBroker.generate(persona + memory + text)
     │        →  { kind:"reply", text }
     └─ "actionable" ─────▶ TASK path  (EXISTING serveSeat/dispatch):
              dispatch(neop, runCase, live) → RunResult → render → { kind:"task", text, meta }
     ▼
  unified ReplyEnvelope  { kind, text, meta? }  ── returned to nc_channels
     ▼
nc_channels.reply_send(text) → _cs_api_call → Synapse → Element      [Wire A — DONE]
```

## Component 1 — the HTTP seat wrapper (`POST /seat/turn`) — the missing destination
A thin Hono/node-http server that wraps `serveSeat` + the new reply path. **Not** the existing CLI.
- **Request** (from the bridge): `{ "message": string, "conversationId": string, "userId": string, "idempotencyKey": string }`. **The payload carries NO scope.** `palaceId`/`neopId` are baked from the wrapper's
  own env (like `palaceClientFromEnv`) — the message is data, scope is identity, and identity is never
  model/payload-supplied. This is the `ADR-wire-b-forwarding` trust-boundary made concrete.
- **Auth (fail-closed, from the ADR bank):** the bridge authenticates to the wrapper — a shared-secret
  `Authorization: Bearer <FORWARD_TOKEN>` (constant-time compare), and later the same Ed25519 posture the
  palace client already carries. **Never an unauthenticated localhost endpoint** anything co-resident can hit.
  Blank `FORWARD_TOKEN` → refuse to start (mirror `ScopeNotConfigured`).
- **Response:** the unified `ReplyEnvelope` (Component 5).
- **T9 gate inherited:** live model/tool execution is T9. The wrapper refuses live runs unless an explicit
  `NEOP_T9_ACK=yes` env is set (the HTTP analog of the CLI's `--i-understand-this-is-T9 yes`) — so standing
  the server up is not itself T9; *serving a live turn* is, and stays gated.

## Component 2 — the intent classifier (NEW; reuse the classifier model slot)
- **Input:** the message text (+ optionally the last N turns of `stm` for context).
- **Output:** `"conversational" | "actionable"` (+ a confidence). `conversational` = a question, chit-chat,
  a memory recall ("what did I tell you about X"). `actionable` = a request to DO something with side effects
  (send an email, schedule, modify state).
- **Model:** the NEop's declared `classifier` model via `ModelBroker` (already required by `schema.ts:39`).
- **FAIL-SAFE DEFAULT — load-bearing:** on low confidence OR classifier error, **default to `conversational`**
  (the non-side-effecting branch). Never default an ambiguous message into a side-effecting task-run. A wrong
  "reply" is a bad answer; a wrong "task-run" is an unapproved side effect. Asymmetric risk → safe default.

## Component 3 — the conversational REPLY path (NEW — this is the memory-backed Bar-2 reply)
The lightweight single-turn path the runtime doesn't have yet:
1. `assembleContext(message)` → palace retrieval (memory-backed; fail-closed — a palace error THROWS, per
   `memory.ts`, and surfaces as a graceful "I can't reach memory right now", never a silent empty).
2. One `ModelBroker.generate({ system: persona + skills, user: message + "# Memory context\n"+retrieval })`
   — a single completion, no plan/execute/verify, no tools, no approvals.
3. → `{ kind:"reply", text }`.
- **Why a new path, not `dispatch`:** `dispatch` is the plan→execute→verify supervisor — too heavy, and it
  can invoke side-effecting tools. A chat reply must be a bounded, tool-less, single generation. Introduce it
  as a sibling to `serveSeat` (e.g. `replySeat(neopPath, {message}, mode) → ReplyEnvelope`), reusing the same
  loader/persona + memory + model brokers. Small, testable, and the direct realization of "answer from memory."

## Component 4 — the TASK path (EXISTING `serveSeat`/`dispatch`) + `RunResult` → reply rendering
- Actionable message → `buildRunCase({task: message})` → `dispatch(neop, runCase, "live")` → `RunResult`.
- **`RunResult` → Matrix reply rendering** (the contract the ADR was missing):
  - `terminalState=DONE` → summarize `taskOutcomes` into a human sentence ("Done — sent the email to …").
  - `terminalState=ESCALATED` / awaiting approval → **surface the approval ask AS a Matrix message**
    ("This needs your OK: <action>. Reply 'approve' to proceed.") — see the open decision below.
  - `terminalState=FAILED` → a graceful failure line + `error`, never a stack trace.
  - Always include `meta: { runId, terminalState, acceptanceAllPass }` for traceability.
- **Phase-1 side-effect containment (recommended):** for the FIRST cut, run the task path with
  `approvals:"deny"` so side-effecting tools **pause and escalate rather than fire**, and the reply is "I can
  do X — it needs approval (not wired yet)." This lets the task path be exercised end-to-end **without any
  live side effect**, deferring the Matrix approval UX to its own design. Keeps the T9 blast radius to
  read-only until you explicitly design approvals.

## Component 5 — the unified `ReplyEnvelope` (so `nc_channels` renders uniformly)
Both branches return the same shape; the bridge doesn't care which path ran:
```
ReplyEnvelope = { kind: "reply" | "task", text: string, meta?: { runId?, terminalState?, intentConfidence? } }
```
`nc_channels` maps `envelope.text` → `reply_send` (its existing `stream_to_text` already handles a string).
No Matrix-specific knowledge leaks into the runtime; no runtime knowledge leaks into the bridge.

## Component 6 — the Python `nc_channels` forward (`reflect=False`)
The bridge side is small: `serve(reflect=False)` (already stubbed) POSTs `{message, conversationId, userId,
idempotencyKey}` to the wrapper with `Authorization: Bearer FORWARD_TOKEN`, reads `ReplyEnvelope`, calls
`reply_send(conversationId, {"stream":[envelope.text]}, txn)`. Construction is unit-testable with an injected
transport (exactly like `_cs_api_call`); the live hop is box-proven.

## Gates & fail-closed posture (carried, not re-derived)
- **T9 STOP-AND-ASK:** serving a live turn (reply OR task) runs a real NEop = T9. Wrapper refuses live unless
  `NEOP_T9_ACK=yes`; you drive the first live turn. Authoring all of the above offline (unit-tested, never
  run live) does NOT cross T9.
- **Scope from env, never payload** (both paths) — mirrors the palace client; the forwarded message is data.
- **Fail-closed everywhere:** blank `FORWARD_TOKEN`/scope → refuse start; palace error → throw → graceful
  Matrix message, never silent empty; classifier ambiguity → conversational (safe) default.
- **Two repos:** the wrapper + reply path + classifier live in `pi-neop-runtime` (its PR); the forward lives
  in `NeuralOPS/nc_channels` (this repo's PR). Each unit-tested independently before any cross-repo live run.

## Open decisions surfaced (for your review — NOT assumed)
1. **Matrix approval UX** (task path, `ESCALATED`/awaiting-approval → how does the user approve in a room?).
   Recommendation: defer — Phase 1 runs `approvals:"deny"` (no live side effects, "needs approval" reply),
   approval UX gets its own design once the reply path is proven.
2. **Streaming vs whole reply.** `RunResult` is whole; the reply path could stream tokens (m.replace edits,
   RISK-1). Recommendation: whole reply first (send-on-complete, the robust default), stream later.
3. **Classifier granularity.** Binary (conversational/actionable) now; a richer intent taxonomy (recall vs
   chit-chat vs multi-step) later if the product needs it.
4. **One NEop or per-seat.** The wrapper serves one baked seat (one `neopPath` + scope) per process, mirroring
   "one shim == one seat." Multi-seat routing is a later concern.

## Build order once approved (all offline/unit-tested up to the T9 line)
1. `pi-neop-runtime`: `replySeat` (Component 3) + intent classifier (Component 2) + `ReplyEnvelope` — unit-tested.
2. `pi-neop-runtime`: the `POST /seat/turn` HTTP wrapper (Component 1) with auth + T9 gate — unit-tested.
3. `NeuralOPS/nc_channels`: the `reflect=False` forward (Component 6) — unit-tested with injected transport.
4. **STOP at T9.** The first live turn (reply path first, task path with `approvals:"deny"`) is yours on the box.
