# Bar 1 (echo through Matrix) — trace these BEFORE building (they change the whole shape)

> Ultrathink on the D-arc gaps, 2026-07-07. Front door connected (Element ↔ real Synapse, `@mansi-neop:neuraledge.in`).
> Two gaps remain to a NEop echoing in Matrix — but they are NOT "just build the ALB + nc-channels.tf per #84."
> #84 is likely **over-scoped for Bar 1**, and there's a runtime subtlety that may gate the echo itself. Trace
> first; build second. **Do NOT author the ALB or serve() until these three are answered.**

## Q1 — Does the echo path in LIVE mode even run on the current runtime? (the load-bearing one)
`orchestrator.handle(..., mode="live")` → `runtime.core.dispatch`. But `core.py` is the **reference/test-mode**
runtime whose `ModelBroker` **RAISES on live tools** (per `ADR-neop-runtime`). The echo NEop (commit #67) runs
**planner/executor/verifier prompts** — i.e. it invokes the LLM. So:
- If echo-in-live needs the LLM and the Python runtime raises on live tools → **Bar 1 (echo) is NOT just "the
  bridge"; it may be gated on the same live-runtime wiring as M1b.** This would be a real, important finding.
- **Trace:** read `runtime/core.py` dispatch in `mode="live"` for the echo folder — does it raise, hit
  OpenRouter, or pass through? This determines whether Bar 1 is reachable on the current runtime at all.

## Q2 — Does the echo need the PALACE? (decides ALB vs co-locate)
An echo reflects the message; it has no reason to query `/mcp`. **If echo needs no palace**, then the whole
cross-VPC/ALB design (#84) is a **Bar-2 concern, not Bar 1** — and the minimal Bar-1 path is far simpler:
- **Co-locate `nc-channels` ON the `matrix-server` box.** Synapse hop = **localhost** (register AS with
  `url=http://localhost:8010`); reply hop = localhost; **no ALB, no ACM, no cross-VPC, no palace.**
- nc-channels there needs only: Synapse (localhost) + (if Q1 says so) OpenRouter egress + key. No spine VPC.
- **Trace:** confirm the echo folder's dispatch makes no `/mcp` call in live mode.

## Q3 — What exactly does `serve()` need, given Q1/Q2?
Only after Q1+Q2: `serve()`/`_cs_api_call` wrap the proven core (`process_transaction`, `reply_send`) in an
`http.server`. Box-gated — **built against the real Synapse, hand-driven, never a mock** (transport-deploy-design D1).
Authoring a draft is fine (it's "wrap the core in HTTP"), but it is PROVEN on the box, iterating on the live
handshake — not completable offline by definition.

## Corrected sequence (next session, fresh context)
1. **Trace Q1+Q2** (read `runtime/core.py` live dispatch + the echo folder) — 15 min, decides everything.
2. If echo runs live + needs no palace → **author draft `serve()` + a co-located run recipe** (nc-channels on
   the matrix box, localhost). Skip the ALB entirely for Bar 1.
3. `[you, box]` register AS (localhost url, corrected regex `@neop_.*:neuraledge\.in`) → run nc-channels →
   iterate `serve()`/`_cs_api_call` against real Synapse → **echo round-trip = Bar 1.**
4. **#84's ALB + spine-VPC nc-channels is Bar-2** (when the NEop needs the palace) — deferred, not deleted.
5. If Q1 says the Python runtime raises on live → Bar 1 itself is gated on live-runtime wiring (M1b-adjacent);
   that's the real finding, and it reorders everything.

## Honest state
The gaps are **box-gated + iterative + have unresolved runtime questions** — they cannot be "completed" from a
dev box, and authoring the ALB/serve() before Q1/Q2 risks building the wrong thing (over-scoped) or a stranded
artifact. The completion is a **focused box session that traces first, then builds the minimal path.**

---
## ANSWERS — traced 2026-07-07 (this changes the plan)
- **Q1 = core.py RAISES on live.** `ModelBroker` (runtime/core.py:165) is unit-only: line 171 raises
  `"mode '<m>' not wired (unit only)"`, line 195 `"live tools not wired"`, memory ops (226-300) support only
  unit/integration. So `handle(mode="live") → dispatch("live") → ModelBroker("live")` **raises**. The echo
  CANNOT run live on the Python runtime. (Unit mode works only for the recorded cassette `echo_hello`.)
- **Q2 = echo needs NO palace.** `agents/echo/tools.json=["echo_tool"]`, mock `{"$reflect_field":"text"}` —
  pure reflection, no /mcp. #84's ALB/cross-VPC is over-scoped for Bar 1; do NOT build it for the echo.
- **⇒ FINDING: Bar 1 (a real NEop echo) is gated on the live Hermes runtime (M1b / pi-neop-runtime), NOT just
  the bridge** — core.py raises on live. Same runtime dependency as Bar 2, minus the palace.
- **Two sub-milestones:** **Bar 1a** = transport proven via a HARDCODED reflection in `serve()` (bridge only,
  no runtime) — achievable next. **Bar 1b** = real NEop echo via handle→dispatch — needs M1b.
- **Corrected next move:** build the bridge for **Bar 1a** (hardcoded reflect, proves Element↔Synapse↔nc-channels
  round-trip), and treat a real-NEop reply (1b/Bar 2) as gated on standing up `pi-neop-runtime` (M1b: GAP-1/GAP-2).
