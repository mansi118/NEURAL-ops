# NEOS / NeuralChat — System Design (as implemented)

What is actually built and green today, at commit `fc69f34`. This is a description of
the running system, not a roadmap — for the forward plan see `BUILD-PLAN.md`.

**One line:** a vertical slice of a multi-agent platform — inbound message → front door
→ a typed-contract agent runtime → streamed reply — where every layer is **offline-gradeable**
and each backend (model, tools, memory, twin, classifier) sits behind a **deterministic seam**
that is recorded in tests and live (credential-gated) in production.

---

## 1. Standing invariants (true everywhere in the code)

1. **Offline-gradeable** — every NEop and layer runs green with no network, no live backend.
2. **Broker seams hide backends** — the agent loop only calls broker contracts
   (`model.call`, `tools.invoke`, `mem.retrieve/write/get_twin`); provider/tool/memory
   internals never leak into the phase machine.
3. **Determinism via recordings** — `unit` mode replays cassettes (model), recorded bundles
   (memory/twin), mocks (tools), recorded fixtures (classifier). A changed input changes a
   hash → forces a conscious re-record.
4. **Structure earns its keep through `nrt` + ACP** — typed phases and the plan artifact exist
   so agents are CI-gradeable and composable, not because the model needs rails. The phase set
   is a function of `role_family`; a pure executor pays no plan/verify tax.
5. **Identity is `(tenant, seat)`; the run seat is the routed NEop**, the human `user_id` rides
   along as `requester` (rate-limit + attribution), never as the memory/twin key.
6. **`core.py` is stable** — the layers above and beside it (`frontdoor/`, `acp/`) only *call*
   `dispatch()`; they never change it.

---

## 2. Architecture

```
 inbound (Matrix / adapter)
        │
 ┌──────▼─────────────────── frontdoor/  (P5 — above dispatch) ───────────────────┐
 │ gateway      normalize → NeuralChatMessage envelope · auth (Matrix token+HMAC)  │
 │              · resolve_identity (tenant, requester) · rate-limit → 429          │
 │ orchestrator classify → (neop, confidence) · COC-1..5 · resolve · stream        │
 │ loader       tenant-override → builtin (agents/) → operator-fallback            │
 │ classifier   recorded fixtures  ⇄  Bedrock / Anthropic Haiku   (gated)          │
 └──────┬──────────────────────────────────────────────────────────────────────────┘
        │  dispatch(folder, msg{text, tenant, seat=routed-NEop, requester}, …)   ← unchanged
 ┌──────▼─────────────────── runtime/core.py  (executable spec) ────────────────────┐
 │ load_neop (diagnostics-as-data)  →  PiAgent run:                                 │
 │   assemble (memory.retrieve + twin prepend, T-5)                                 │
 │   → plan → execute (DAG: topological order by depends_on + output threading)     │
 │   → verify → run_end (memory.write + consolidate + shadow)                       │
 │   phase set = f(role_family) · 11-state machine (4 terminal) · bounded           │
 │   replan → escalate · typed event stream                                         │
 │                                                                                  │
 │   deterministic broker seams        unit (recorded)        integration (live)    │
 │     model   ModelBroker             cassettes          ⇄    LLM                   │
 │     tool    ToolBroker              mocks + allowlist  ⇄    runtime/aws.py (boto3)│
 │     memory  MemoryBroker            recorded bundles   ⇄    runtime/memory.py     │
 │     twin    (MemoryBroker.*_twin)   recorded twin      ⇄    Convex structured rec │
 └──────────────────────────────────────────────────────────────────────────────────┘
        ▲
 ┌──────┴─────────────────── acp/  (Flow 7 — beside the runtime) ───────────────────┐
 │ coordinator → Ed25519-signed envelope → router (ACP-1 sig+schema · ACP-2 cycle · │
 │ ACP-3 hop≤5 · ACP-4 capability) → dispatch(B)  ·  B runs under its OWN seat       │
 │ capabilities registry (frontmatter acp.publishes) · chain runner (COC-5)         │
 └──────────────────────────────────────────────────────────────────────────────────┘

 nrt/cli.py  validate·test·trace·suite (tester)     tools/new_neop.py  scaffold generator
 tests/      broker + layer unit tests              agents/            9 NEops
 docs/       NE-TSD S1/S2/S3 specs                  BUILD-PLAN.md      canonical phase tracker
```

---

## 3. The deterministic-seam pattern (the central idea)

Every external dependency is reached through a broker/seam with two resolutions:

| Seam | Contract | unit (recorded) | integration (live, gated) |
|---|---|---|---|
| **Model** | `model.call(phase, prompt)` | `fixtures/cassettes/<case>.json` (bootstrap-tolerance) | LLM |
| **Tool** | `tools.invoke(tool, args)` | `fixtures/mocks/tools.json` + allowlist | `runtime/aws.py` (read-only boto3) |
| **Memory** | `mem.retrieve/write(tenant, seat, …)` | `fixtures/memory/<case>.json` | `runtime/memory.py` → Mempalace_NEOS `/mcp` |
| **Twin** | `mem.get_twin/put_twin(tenant, seat)` | `fixtures/twin/<case>.json` | Convex structured record |
| **Classifier** | `classify(text) → (neop, conf)` | recorded `(text→neop,conf)` | Bedrock / Anthropic Haiku |

The phase machine never knows which side it's on. That is what makes the whole system
CI-gradeable: `nrt` proves the contract; the live side only needs credentials + a smoke.

---

## 4. Components

### `runtime/core.py` — the executable spec (production "Hermes" mirrors it)
- **Loader** `load_neop` → `(defn, diagnostics)`; collects *all* defects (errors+warnings), never
  throws on first; enforces the tool allowlist (frontmatter `tools` ⊆ `tools.json`).
- **State machine** — 11 states, 4 terminal (`DONE/FAILED/ESCALATED/REJECTED`).
- **Phase sets by `role_family`** — `meta/sales/research`: plan→execute→verify · `reactive`:
  execute→verify · `executor`: execute only.
- **PiAgent loop** — `assemble` (memory retrieve + twin prepend) → plan → **DAG execute**
  (topological order by `depends_on`, each task's output threaded into dependents) → verify →
  `run_end` (memory write + `consolidate()` STM→LTM hook + non-blocking `shadow_prediction`).
- **Brokers** — Model (cassette), Tool (mock + runtime allowlist → `tool_blocked`), Memory
  (recorded bundles, tenant guard, content-derived idempotent dedup, twin get/put with
  versioning + stale-`base_version` rejection).
- **Typed event stream** — `run_start, assemble, memory_retrieve, twin_assembled, plan_*,
  tool_call/result/blocked, verify_*, memory_write, twin_written, shadow_prediction, replan,
  escalate, run_end`. Powers `nrt trace`, assertions, future UI.
- **`dispatch(folder, msg, mode, cassette, mocks, stm, memory, twin)`** — the one entrypoint.

### `runtime/aws.py` · `memory.py` · `twin.py` — live adapters (lazy, credential-gated)
- **aws** — read-only boto3 registry (`sts_whoami`, `s3_list_buckets`, `dynamodb_list_tables`).
- **memory** — HTTP client to **Mempalace_NEOS** Convex `/mcp` (`palace_search` / `palace_remember`);
  Convex SoT + FalkorDB + Voyage embeddings (server-side). Gated on `CONVEX_DEPLOYMENT_URL`.
- **twin** — seed schema + `validate_twin` + `twin_preamble` (the T-5 prompt prepend).

### `nrt/cli.py` — the runtime tester
`validate` (diagnostics) · `test` (assert on typed result) · `trace` (event stream) · `suite`.
Assertion engine: terminal state, structural-plan diff *including edges*, tool allowlist
(must/​must-not call), phase set, memory chunk ids / wrote, twin version/maturity, shadow agreed,
replan budget, latency.

### `frontdoor/` — the front door (P5, above `dispatch`)
`gateway` (envelope/auth/identity/429) · `loader` (override→builtin→fallback) · `orchestrator`
(classify, COC-1..5: 0.7 gate, disambiguation, `@mention` bypass, chain guard; resolve →
dispatch → token stream) · `classifier` (recorded ⇄ Bedrock/Anthropic seam).

### `acp/` — agent communication protocol (Flow 7, beside the runtime)
`envelope` (build / **Ed25519** sign+verify / deterministic keyring) · `capabilities` (registry
from `acp.publishes`) · `router` (ACP-1..4 gates → `dispatch(B)`; B runs under its own seat,
sender = requester; refuse is a signed envelope; `parent_envelope_id` audit chain) · `chain`
(COC-5-gated coordinator; one signed delegate per hop, outputs threaded).

### `tools/new_neop.py` — scaffold generator
Generates a NEop **born memory+twin-attached** (`memory:{read}` + `twin:{read}`, write
deliberate); `--harness` for memory-less instruments. Output is green under `nrt` immediately.

### `agents/` — the NEop catalog (9)
| NEop | role_family | posture | proves |
|---|---|---|---|
| echo | meta | harness | runtime contract (hello-world) |
| ping | executor | harness | phase set = f(role_family) (execute-only) |
| aws-probe | executor | harness | AWS tool seam (read-only) |
| recon | sales | memory+twin read | DAG executor (3-task, edges, threading) + replan→escalate |
| cortex | meta | memory r/w + twin read | memory seam read→use→write, tenant guard, dedup |
| interviewer | meta | memory read + twin **write** | twin v0 (seed) via `put_twin` |
| decision-shadow | reactive | twin read + shadow | non-blocking prediction (Flow 5) |
| researcher | research | memory+twin read | ACP chain link (scaffolded) |
| proposal-writer | meta | memory+twin read | ACP chain link (scaffolded) |

---

## 5. Request lifecycle

**Single message (Flow 2/3):** inbound → `gateway` (auth, resolve `(tenant, requester)`,
rate-limit) → `orchestrator` (classify → `(neop, confidence)`; COC-4 `@mention` bypass / COC-2/3
0.7 gate / COC-5 chain guard) → `loader` resolves the NEop folder → `dispatch(folder, msg)`
with `seat = routed NEop`, `requester = human` → PiAgent runs (assemble→plan→execute→verify) →
token stream back. Non-agent overhead is measured and excludes `dispatch`.

**Composition (Flow 7):** a coordinator builds an Ed25519-signed `delegate` envelope per hop,
the `router` verifies (ACP-1..4) and routes to `dispatch(B)`; B runs under its own seat with the
sender as `requester`; each NEop's outputs thread into the next hop; the audit chain reconstructs
via `parent_envelope_id`. Proven: **Recon → Researcher → Proposal Writer**, COC-5 gated.

---

## 6. Identity & provenance

`tenant` (palaceId) + `seat` (neopId). The run **seat is the routed NEop** — it keys *that NEop's*
memory and twin. The human `user_id` is the `requester`, carried for rate-limit + attribution,
never the memory key (proven across the front door **and** across an ACP delegation hop). Memory
writes stamp `source_adapter / source_external_id / author_*`; the ACP audit log links hops.

---

## 7. Testing & gradeability

- **`python3 nrt/cli.py suite agents`** — agent-level, every NEop (**12 cases green**).
- **`tests/test_{memory,twin,frontdoor,acp}.py`** — broker/layer units (tenant guard, dedup
  idempotency, twin versioning + stale-base, COC-1..5, gateway 429/auth, ACP gates + cross-hop
  identity semantic + the chain). All green.
- **`tests/smoke_classifier.py`** — gated live recorded-vs-live agreement (skips without a key).

---

## 8. Implementation status

| Capability | State |
|---|---|
| Runtime contract + DAG executor + `nrt` (P1–P2) | ✅ green |
| Memory broker over MemPalace + twin v0 + Decision Shadow (P3–P4) | ✅ green (offline) |
| Front door: gateway + orchestrator + loader (P5) | ✅ green |
| AWS tool seam | ✅ green (read-only) |
| Memory+twin default posture + scaffold generator | ✅ green |
| ACP composition — signed router + Recon→Researcher→Proposal chain (Flow 7) | ✅ green |
| Memory adapter pointed at Mempalace_NEOS (Convex + Voyage) | ✅ adapter aligned |
| **Live classifier verdict** | ⛔ gated (Anthropic key / Bedrock use-case form) |
| **Live `palace_search` read smoke** | ⛔ gated (Convex creds + go-ahead) |
| **Twin live get/put** — `palace_get_closet` in Mempalace_NEOS | ⬜ queued (cross-repo) |
| **Vault promotion (Flow 4)** — VL-1 confidence · VL-2 PII redact · VL-3 provenance · VL-4 approval queue · VL-5 rollback-armed | ✅ green (offline; layer over broker writes, core untouched) |
| Twin Curator / fidelity clock (Flow 6) — seed→growing→mature via corroborated signals | ✅ green (offline; 5 gates incl. holds, injected clock = deterministic, core untouched) |
| **Automation flywheel (Flow 8)** — FW-1 recurrence · FW-2 success-bias · FW-3 novelty · FW-4 approval queue · FW-5 spec-only (no auto-spawn) | ✅ green (offline; observe→surface→approve→NEop-spec, conservative bias, core untouched) |
| RRF retrieval · multi-tenant ACL · DAG chains | ⬜ deferred (on demand) |

Everything ✅ is offline-green and pushed to `origin/main`. Everything ⛔ waits only on a
credential/account action; everything ⬜ is agent-buildable on demand.
