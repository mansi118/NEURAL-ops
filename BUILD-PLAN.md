# NEOS / NeuralChat — Build Plan (canonical tracker)

Tracks against **NE-BUILD-NC-V1**. One thin vertical slice through the stack, then thicken.
This file records the **locked contracts, status, and decisions** per phase so the repo stays
canonical. Detail lives in NE-TSD-NC-V2 S1/S2/S3.

## Standing invariants (never relax)

1. **Offline-gradeable** — every NEop green under `nrt` with no network / no live backend.
2. **Broker seams hide backends** — PiAgent only calls `model.call`, `tools.invoke`, `mem.retrieve/write`.
3. **Determinism via recordings** — unit mode replays cassettes / recorded bundles / mocks.
4. **Structure earns its keep through `nrt` + ACP**, not the model. Phase set = f(`role_family`).
5. **Trace-before-build, gate-by-gate, verify-before-trust.**
6. **Dogfood one seat** (NeuralEDGE = alpha tenant #1).
7. **No build step mutates prod.** Live integration is read-only and gated; writes stay unit-only.

## Phase status

| Phase | Status | Seam forced |
|---|---|---|
| P1 runtime + nrt | ✅ done | state machine + 3 brokers + typed event stream |
| P2 Recon (DAG) | ✅ done | executor: topo-order by `depends_on` + output threading |
| P3 Memory (MemPalace) | ✅ done | MemoryBroker (3rd seam) + assemble/run_end + memory events |
| P4 Twin v0 + Interviewer + Shadow | ✅ done | NEop-output-as-context (assemble prepends `twin.md`) |
| P5 Front door | ✅ done | gateway + orchestrator above `dispatch()` (core untouched) |

## Locked contracts

### Runtime (P1/P2)
- States: 11 (4 terminal: DONE, FAILED, ESCALATED, REJECTED). Loader = diagnostics-as-data.
- `dispatch(folder, msg, mode, cassette, mocks, stm, memory=None)`.
- Executor runs `depends_on` in topological order; each task's output threads into dependents'
  input scope keyed by upstream `task_id`.

### Memory (P3) — **MemPalace = façade over Convex (SoT) + Bedrock Titan v2 (1024-d); FalkorDB advisory**
- Identity is **two fields**: `tenant` = palaceId (e.g. `neuraledge`), `seat` = neopId (e.g. `aria`).
  (Supersedes the S2 single-`seat` signature.)
- Contract:
  - `retrieve(tenant, seat, query, tiers={}, k=5) -> {chunks, provenance}`
  - `write(tenant, seat, record) -> {status, closet_id, dedup_key}` — broker stamps
    `source_adapter`, `source_external_id`, `author_*`.
  - `consolidate(tenant, seat)` — STM→LTM hook, thin body, real call site.
- `tiers` has **no MemPalace equivalent** (STM/LTM implicit) → documented **no-op passthrough**, kept
  for forward-compat.
- **Dedup is content-derived** → identical writes share a `dedup_key` and the duplicate is a noop
  (idempotent). Mirrors MemPalace `sha256(sourceAdapter + sourceExternalId)`.
- **Tenant guard** in the broker (defense-in-depth; Convex also pre-filters): tenant A never reads
  tenant B's chunks. Proven by `agents/cortex/.../cortex_isolation` + `tests/test_memory.py`.
- Modes: `unit` = recorded bundles `fixtures/memory/<case>.json`; `integration` = `runtime/memory.py`
  HTTP to `{CONVEX_SITE_URL}/mcp`, lazy + gated on `CONVEX_SITE_URL` + `AWS_BEARER_TOKEN_BEDROCK`.
- **Live-smoke policy:** read-only `palace_search` against a scratch `neopId` **only**, never
  `palace_remember`, and only on explicit go-ahead. Default = deferred, unit-only.
- Deferred: RRF/BM25/graph/recency fusion, Vault promotion, nightly consolidation cron,
  Gemini→Qwen3 embedding migration (current = Bedrock Titan v2).

### Twin (P4) — Twin v0 + Interviewer + Decision Shadow  [✅ done]

Forces: NEop-output-as-another's-context (first time). Seam: twin methods on the shared
Convex client (segregated interface) + assemble prepend + non-blocking shadow path.

- **twin.md** — YAML frontmatter (`twin_id: tenant:seat`, `version`, `maturity`,
  `fidelity_score`, `identity`/`communication`/`decision_style`, `signals{}`) + markdown body.
  Convex SoT, keyed `tenant:seat`, versioned-on-change with diffs.
- **Twin access (NOT `palace_search`)** — definite fetch of one versioned doc, kept behind a
  named interface, out of the chunk retrieve/write paths (so a `TwinBroker` extraction stays mechanical):
  - `get_twin(tenant, seat) -> twin | None`
  - `put_twin(tenant, seat, twin) -> {status, version, maturity, diff_id}` — bumps version,
    preserves `signals`, rejects stale `base_version` (optimistic concurrency) + invalid schema.
- **Assembly order (T-5, load-bearing):** session = `tenant_ctx · twin.md · STM · PALACE`,
  twin prepended to the prompt before the model call. No twin → prior NEops unchanged.
- **Opt-in** via frontmatter `twin: {read, write}` (mirrors P3 `memory:`); non-opted NEops make
  no `get_twin` call and emit zero twin events.
- **Events:** `twin_assembled` (read), `twin_written {seat, version, diff_id}` (write),
  `shadow_prediction {predicted, actual, agreed, class}`.
- **role_family:** interviewer = `meta` (verify = schema validation); decision-shadow = `reactive`.
- **Non-blocking shadow:** terminal state set **before** shadow emits (structural guarantee) +
  `max_latency_s` assertion. Proven by `agents/decision-shadow` (agree + diverge).
- **Deferred (traps):** fidelity clock (seed→growing→mature, ≥0.65/30d), Twin Curator, drift/re-tune
  UI, NATS `signals.*`, Redis cache, 80-question depth, live decision-shadow storage.
- **Safety:** unit-only; no live twin writes to prod Convex; read-only `get_twin` smoke against a
  scratch seat only on explicit go-ahead.

### Front door (P5) — nc-gateway + nc-orchestrator  [✅ done]

Forces: first concurrent, latency-bound surface. Lives in `frontdoor/` **above** `dispatch()`;
`core.py` / the `dispatch()` signature / the agent loop are **untouched** (orchestrator only calls dispatch).

- **Envelope** `NeuralChatMessage`: `msg_id, tenant_id, channel, conversation_id, thread_id,
  user_id ("tenant:seat"), text, attachments, mentions[], ts, metadata`.
- **Identity threading (the pin) — run seat ≠ requester:** `tenant` ← envelope; **run `seat` ← the
  routed NEop** (classification / `@mention`) — it keys *that NEop's* memory + twin; the human
  `user_id` rides along as **`requester`** (rate-limit + attribution), **never** as the memory/twin key.
  Threaded into the dispatch msg with **zero `dispatch()`/`core.py` change**. Proven by a
  differing-requester case: `neuraledge:ml` invokes `@cortex` → memory provenance `author_id=cortex`
  (not `ml`).
- **Gateway:** `normalize` → envelope; `authenticate` (Matrix token + adapter HMAC, presence-checked
  offline); `resolve_identity → (tenant, requester)`; `RateLimiter` — **60 msg/min/requester** active;
  the **16 concurrent/tenant** cap is a deterministic in-flight counter (`enter`/`leave`), wired at
  integration (not auto-driven in the sync unit path).
- **Orchestrator (COC-1..5):** `classify → (neop, confidence)` (recorded seam unit / live integration);
  ≥0.7 dispatch else 1 disambiguation (COC-2/3); direct `@mention` bypass (COC-4); `+`-chain guard
  needs `explicit_intent` (COC-5).
- **Loader resolution:** `tenant-override → builtin (agents/) → operator-fallback`, first match wins.
- **Latency boundary (NFR-1):** `overhead_ms` measures gateway+route+resolve and **excludes** dispatch
  (Pi-agent work). The unit number is a near-zero **floor** proving the boundary; the actual
  p50≤800ms / p95≤2s budget is an **integration** SLO, not something the unit gate proves.
- **Deferred (traps):** four-layer ACL / multi-tenant isolation theater, SSO/OIDC, real Matrix/NATS/
  Sliding-Sync, automation-flywheel receive side, nc-web beyond a stub. Single seat dogfooded first.

## Testing
- `python3 nrt/cli.py suite agents` — agent-level (every NEop).
- `python3 tests/test_memory.py` — broker-level units (dedup idempotency, tenant guard).
- `python3 tests/test_twin.py` — broker-level units (versioning, signal preservation, stale base, schema).
- `python3 tests/test_frontdoor.py` — front-door units (gateway/429/auth, COC-1..5, loader, round-trip, identity threading).
