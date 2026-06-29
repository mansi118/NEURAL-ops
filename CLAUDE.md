# CLAUDE.md — neop-jcode-adapter

You are implementing the NEop⟷jcode harness adapter. Read
`docs/neop-jcode-adapter-implementation-plan.md` first and follow §4 in order.

INVARIANTS (do not violate — see plan §1):
- Memory = CORTEX-PALACE ops only (palace_search / palace_remember / [palace_get_closet after T8]).
- Scope is (palaceId, neopId); NEVER accept scope from the model. The shim bakes + signs it.
- ACL is **fail-CLOSED on the deployed spine** (S0.3 live — verified at T0 2026-06-29: an unseeded seat is
  DENIED at `enforce.ts:80`, not fail-open as the plan assumed). The container jail is **defense-in-depth,
  proven at live T7** (egress confined to the palace; metadata + internet blocked; rootfs RO; caps dropped).
  Do not weaken either.
- jcode is configured, never forked. The runtime NEop LLM is **OpenRouter** (D2 shipped, M2 #46;
  `OPENROUTER_API_KEY`) **by decision** — NOT because Bedrock is blocked. **Bedrock works in-VPC** (verified
  at T0): generative invoke via **Nova** (`apac.amazon.nova-lite-v1:0`, bearer-token bedrock-runtime
  endpoint — now serves **ingestion extraction**) AND **Titan embeddings** (live, ranked retrieval 0.986).
  The ONLY genuine Bedrock block is **Anthropic models** (use-case form not submitted) — model-specific,
  NOT account-wide. See `docs/decisions/embedder-as-built.md` + `docs/decisions/ADR-llm.md`.
- Internal tenant only; no client data until T7 (red-team isolation) passes.

WORKFLOW:
- Implement one task at a time; run its tests before moving on.
- STOP and ask before T9 (first real NEop) and before any task that would touch client data.
- T1 and T8 are independent and may be parallelized; T2→T3→T4 are sequential.

---

## VERIFIED REALITY (traced 2026-06-18 against live Mempalace_NEOS / NEURAL-ops — do not re-derive)

Three corrections to the plan's stated invariants, confirmed against the actual repos. Build to THESE:

1. **`/mcp` does NOT verify any signature today.** `convex/access/enforce.ts:316` states signed
   `X-NEop-Identity` is DEFERRED (Gate D, to S0.3+); `convex/http.ts:75` resolves identity as
   `neopId = body.neopId ?? header "X-Palace-Neop" ?? "_admin"`. ⇒ The shim's Ed25519 signing is
   **forward-looking defense-in-depth, NOT a live trust boundary.** The enforced v1 guarantees are
   (a) scope baked from env + **fail-closed on blank scope**, and (b) the container egress jail.
   SHARP EDGE: missing scope defaults to **`_admin`, which BYPASSES all ACL** — so the shim must
   ALWAYS set neopId (body + `X-Palace-Neop` header) and refuse to start on blank PALACE_ID/NEOP_ID.

2. **The real `/mcp` request contract** (verified via `tools/dogfish_acl_smoke.py`), NOT the plan's
   `{**args, palaceId, neopId}` pseudocode:
   `POST {PALACE_MCP_URL}` body = `{"tool": <name>, "palaceId": <pid>, "neopId": <seat>, "params": <args>}`,
   header `X-Palace-Neop: <seat>`. Tool args go under **`params`**, and `tool` is a top-level field.

3. **`palace_get_closet` (by-id):** the underlying Convex query `getCloset(closetId)` ALREADY exists
   (`convex/palace/queries.ts:143`), but it is **not registered as an `/mcp` tool**. So T8 is smaller
   than the plan assumed — only the MCP tool dispatch case + ACL wrapper. Keep it GATED in the shim
   until T8 ships (`enable_get_closet=False` by default).

Other confirmed facts: `runtime/memory.py` gates on `CONVEX_DEPLOYMENT_URL or CONVEX_SITE_URL` (the
`.convex.site` HTTP-actions endpoint — NOT `.convex.cloud`); runtime LLM = **OpenRouter** (D2/M2) by
decision. **Bedrock works in-VPC** (T0-verified): Nova generative (ingestion extraction) + Titan embeddings
(retrieval 0.986); only **Anthropic-on-Bedrock** is gated (use-case form). "Bedrock blocked account-wide"
is FALSE — do not re-derive it.
jcode = `1jehuang/jcode`@`master` (reference/runtime — configured, never forked);
the full git clone is flaky on this link — read files via `https://raw.githubusercontent.com/1jehuang/jcode/master/<path>`.

## JCODE INTERFACE (traced 2026-06-18 from jcode@master — config_render built to THIS, not the plan's examples)
- **Config dir = `$JCODE_HOME`** (default `~/.jcode`); main config = `$JCODE_HOME/config.toml`. No `--config` flag.
- **Provider for a direct Anthropic key = `default_provider = "anthropic-api"`** (the bare string
  `"claude"` is OAuth/subscription, NOT a key). NO `[providers.claude] type="anthropic"` — `[providers.X]`
  is only for openai-compatible/openrouter gateways. Key read from env automatically; never write it to
  config. Valid pinned id: `claude-opus-4-8`.
- **MCP = separate JSON `$JCODE_HOME/mcp.json`** (also `./.jcode/mcp.json`, `./.claude/mcp.json`), top
  key `servers`, per-server `{command,args,env,shared}`; **`shared` defaults TRUE → force `false`** for
  the per-seat stateful shim. jcode launches `command` stdio MCP subprocesses (standard JSON-RPC).
- **No four-tier safety config.** Shipped `[safety]` = notifications only. Real gating = `[tools].enabled/
  .disabled` + `[hooks].pre_tool` (exit 2 = block). Adapter renders tiers → `[tools].disabled`
  (Class B/C → `["bash","browser","swarm"]`; A → `["browser"]`); the ask/allow dynamic tier = the
  pre_tool hook (T5). `sandbox_only` tools stay enabled — the CONTAINER is the sandbox.
- **CLI:** `jcode run "<prompt>"` (one-shot), `jcode serve` (daemon), `jcode --resume <session_id>`
  (a "seat" == a session id). **Memory graph is DURABLE** at `$JCODE_HOME/memory/` (not ephemeral);
  export via `jcode memory export <out> --scope project|global|all` (feeds MemoryPromoter T6).
- **Open Decision §8.1 RESOLVED:** jcode "OpenClaw" = its iOS-app / Ambient-Mode brand, NOT a shared
  protocol/Hermes spine → the adapter does NOT get thinner; scope stays full.

## ENVIRONMENT GATES (cannot be run in this WSL dev box — USER/box-gated)
- **T0 (go/no-go spike)** needs a runnable jcode binary + live `ANTHROPIC_API_KEY` + live palace
  deploy + Docker. None exist here (no Docker in WSL; palace deploy is the user's `CONVEX_DEPLOY_KEY`
  gate). T0 must pass on the target box (EC2/Mac-mini) before T1 integration / T2+ are validated.
- Offline-gradeable now: T1 shim unit tests (scope-lock, allowlist, signing), safety-tier data,
  seat-class presets. Everything touching containers/live palace/jcode is box-gated.

## DISCIPLINE (inherited from the NEOS project)
Trace-before-build; surface missing pieces as blockers, don't code past them. `runtime/core.py`
stays byte-identical. NEURAL-ops = branch + PR, confirm-before-push. One task at a time, tests green
before moving on.
