# ADR-neop-runtime — What runs a NEop's inner agent loop

> **Status:** DECIDED 2026-06-30 — verified by runtime trace (see "Hermes runtime trace" below); ML chose
> the M1b path · **Owner:** ML
> **Date:** 2026-06-30 · **Confidentiality:** CONFIDENTIAL — INTERNAL (NeuralEDGE)
> **Supersedes:** the NEop-runtime framing of `docs/neop-jcode-adapter-implementation-plan.md` (§0 line 17, §262)
> **Leaves intact:** the NEOS canon (`SKILL.md`), `ADR-llm.md` (LLM provider is orthogonal to runtime)

---

## Why this ADR exists

The record carried a **direct, never-adjudicated contradiction** about the single most load-bearing
question in the system — what executes a NEop's reasoning:

- **Canon (`.claude/skills/neos-implementation/SKILL.md:77`, `:80`, `:123`):** *"A **NEop** = a folder of
  Markdown (SOUL/PROTOCOLS/TOOLS + `openclaw.json`) running as a provisioned **Hermes agent instance**."*
  *"Hermes ≡ OpenClaw. One runtime, two names."* → **Hermes IS the inner agent loop.**
- **The build-ready plan (`docs/neop-jcode-adapter-implementation-plan.md:17`, `:262`):** *"a thin
  neop-jcode-adapter … lets a NEop run its inner agent loop on **jcode** … jcode owns only the per-seat
  agent loop."* / *"Build the adapter as **the layer you run NEops on with jcode** — not a replacement for
  the OpenClaw/Hermes spine."* → **jcode IS the inner agent loop.**

Document-versus-document has no resolution procedure: whichever document a given session happened to be
reading won that session, and the work drifted toward jcode-as-NEop-runtime because the *plan* is the
written, build-ready artifact while the resolution favouring Hermes stayed **conversational and was never
written down**. This ADR resolves the contradiction by grounding the decision in **what the running code
actually does**, so it cannot be re-litigated on either document's authority — both documents become
*consequences* of a verified fact, and a fact does not take sides on re-read.

## The drift mechanism (named, so it can't recur)

The plan's thesis line (`:262`) re-scoped one word. Canon says Hermes is *the runtime a NEop runs as*; the
plan reassures that jcode is "not a replacement for the OpenClaw/Hermes **spine**" — silently demoting
"Hermes" from *the inner loop* to *the orchestration spine that wraps the inner loop*, which vacated the
runtime slot for jcode. The single place the plan touches jcode-vs-Hermes (`:239`) only asks whether they
share *lineage* (to make the adapter thinner) — it **never poses** the question *"should a NEop run on jcode
instead of Hermes at all?"* That question was never in the record until now.

## What the code actually shows (the decision driver — verified, file:line)

Traced in `NEURAL-ops` + `Mempalace_NEOS` (this session), 2026-06-30:

1. **No native NEop agent loop exists in these two repos.** `runtime/core.py` is an orchestrator +
   phase-state-machine + approval router — *not* a prompt→LLM→tool→observe→repeat loop. Its `ModelBroker`
   runs cassette/unit-mode only and **raises** on live tools (`"live tools not wired in step-1 reference"`);
   the `PiAgent` class there is a test-mode reference shadow, not the Pi runtime. `core.py` is the
   byte-frozen reference, by design (its own header: *"reference / test-mode"*).
2. **jcode is the only inner-loop vehicle wired in these repos**, and even it is box-gated here:
   `neop_jcode_adapter/supervisor.py` → `_spawn` raises `NotImplementedError("box-gated: launch jailed
   jcode via IsolationUnit (T0 box)")`. jcode is external (`1jehuang/jcode@master`, Rust), "configured,
   never forked" (`plan:17`).
3. **`NE-QuickBuild` does not exist in code** — not a NEop, not a capability, not config, in either repo
   (only in TSD/roadmap diagrams). So the "jcode = QuickBuild build-assist only" resolution was unwritten on
   *both* ends: the decision was never recorded **and** its intended destination was never built.
4. **A runnable native Hermes/Pi NEop runtime EXISTS and was traced** — `mansi118/pi-neop-runtime`
   (TypeScript, built on `@earendil-works/pi-agent-core` + `@earendil-works/pi-ai`), named by ML and
   verified 2026-06-30. Three-child results in the next section.
5. **Caveat that drove the trace, now confirmed:** the contract-conformance between the Python reference
   (`runtime/core.py:4-6`: *"Production Hermes (Node) implements the same contract"*) and the production
   runtime was **asserted in prose, never verified by shared code** — no dependency, submodule, image, or
   import links them, and per `README.md:123` not even `nrt` integration cassettes exist yet. The trace
   below replaces that assertion with evidence — and the evidence is that they have **diverged on the one
   contract that matters** (`/mcp`).

## Hermes runtime trace (`pi-neop-runtime`, verified at file:line 2026-06-30)

Standard locked **before** evidence: all three children green → DECIDED, M1b on Hermes; **any one red → that
red is the named blocker → gated work with a written trigger, not a coin-flip.**

| Child | Verdict | Evidence |
|---|---|---|
| **1 — real prompt→LLM→tool→observe loop** | 🟢 GREEN | Real pi Agent via `@earendil-works/pi-agent-core` (`package.json`); `src/brokers/model.ts:123-142` `resolveLiveModel()` resolves a live Anthropic model + requires `ANTHROPIC_API_KEY`; `src/supervisor.ts:93-178` runs a real plan→execute→verify loop delegating to Agent runs (`src/subagents.ts`); typed event stream + `AWAITING_APPROVAL` wired (`supervisor.ts:118-125`). A genuine runtime, materially more than `core.py` glue. |
| **2 — `/mcp` spine contract** | 🔴 **RED** | `src/brokers/memory.ts:23` live PALACE retrieval = `throw "live PALACE retrieval not wired in this dev build"`; `write()` is a no-op array sink (`:27-29`); **no** `{tool,palaceId,neopId,params}` body, **no** `X-Palace-Neop` header, **no** scope-bake / sign / ACL anywhere. (Partial credit: typed events + approval present; **memory + identity/ACL are not**.) |
| **3 — jailable** | 🟡 AMBER | No container/egress-jail artifact in-repo (no Dockerfile / iptables / seccomp / cap-drop); app-level allowlist + default-deny only via the Agent `beforeToolCall` hook (`src/brokers/tool.ts:1-8`). Feasible to jail (plain Node app; the T7 egress spec is process-agnostic), **not demonstrated**. |

**The asymmetry the trace exposed:** T0's live GO (write→Nova→Titan→retrieval 0.986) proved the `/mcp`
contract **for the jcode path** (the `palace_mcp_shim`), **not** for Hermes. The canonical runtime
(ratified by child-1) cannot do the one thing T0 proved; the runtime T0 proved it on (jcode) is the one this
ADR declines as the general NEop runtime. **The T0 GO does not transfer to Hermes** — Hermes must earn its
own. This is the divergence anticipated when the ADR was PROPOSED, now confirmed at `memory.ts:23`.

## Decision

**The NEop inner-loop runtime is Hermes.** Canon is ratified, because Hermes exists and runs a **real**
agent loop — verified at child-1 (`pi-neop-runtime` on `@earendil-works/pi-agent-core`), not an aspirational
spec. A NEop is a provisioned Hermes agent instance, as `SKILL.md:77` states.

**jcode is NOT sanctioned as a general NEop runtime.** Running NEops on jcode was an undocumented
substitution against live canon, with no written rationale anywhere in the record. jcode's sanctioned role
is narrowed to the **gated NE-QuickBuild build-assist capability** (code-generation / build-and-deploy
seats), behind the same isolation gates already proven at T0/T7. This is where the T0/T7 investment
**transfers and is preserved**, not wasted — when NE-QuickBuild is actually built.

**The plan's NEop-runtime framing (`:17`, `:262`) is superseded** by this ADR. The plan's *spine* work
(identity, ACL, audit, events, palace-backed memory, the scope-baked/signed shim, the container jail) is
**not** superseded — that orchestration is runtime-agnostic and stands.

## Consequences (stated honestly, including the costs)

- **Canon is NOT corrected.** `SKILL.md` / the TSD runtime model stand as written — Hermes is the runtime.
  (Contrast the Bedrock/fail-open reconciliation, where the record bent to the work; here the *work* bends
  to the record, because the record was right.)
- **`docs/neop-jcode-adapter-implementation-plan.md` gets a `superseded-by: ADR-neop-runtime` banner** on
  its NEop-runtime framing (§0, §262, invariant references that call jcode the NEop loop). Its spine/jail
  content remains valid and should be re-pointed at "the QuickBuild build-assist seat" rather than "the
  NEop you run."
- **M1b is BLOCKED on two parallel, named Hermes gaps — jcode's T0/T7 proof does NOT transfer** (ML chose
  the "port + parallel jail-prep, no jcode bridge" path). Both must turn green before M1b runs:
  - **GAP-1 (child-2, `/mcp` spine contract):** port the `palace_mcp_shim` contract (scope-bake + Ed25519
    sign + ACL-respecting `{tool,palaceId,neopId,params}` + `X-Palace-Neop`) into `pi-neop-runtime`'s
    `src/brokers/memory.ts` (today 30 LOC, throws on live), then prove it with a **T0-equivalent live memory
    run on Hermes** — ranked retrieval, **empty=FAIL** (inherits `embedder-as-built.md:18`). **Trigger:**
    that run is green.
  - **GAP-2 (child-3, isolation):** containerize Hermes under the **T7 egress-jail spec** (the spec is
    process-agnostic; the artifact must be built for the Node runtime), then a **Hermes-native isolation
    proof equivalent to live T7**. The jcode jail result does NOT stand in for the Hermes one. **Trigger:**
    that proof is clean.
  - **No jcode bridge:** jcode runs no NEop seats in the interim; it stays QuickBuild-build-assist-only.
    M1b starts only when GAP-1 ∧ GAP-2 are both green.
- **The M1b acceptance bar is unchanged and applies to the Hermes path:** ranked real-memory retrieval as a
  *pass condition*, **graceful-empty as FAILURE** — inheriting the embedder done-bar
  (`docs/decisions/embedder-as-built.md:18`). The T0/spine smokes passed partly on graceful-empty tolerance;
  M1b is where that tolerance must invert.
- **The isolation passage still stands, now homed on Hermes:** tenant isolation is proven
  *by-construction* (scope baked + signed; fail-closed ACL) and by *single-tenant* T7 — **NOT** by a live
  adversarial cross-REAL-tenant attempt (only one tenant palace exists). That two-palace red-team gates any
  second real tenant, regardless of runtime. M1b success must not read as "isolation proven live."

## Resolution (decided 2026-06-30)

The open input — *"is there a concrete blocker making Hermes unusable for M1b right now?"* — was answered by
the trace, **on evidence, not recollection:** YES, child-2 is red (`memory.ts:23`). Per the locked standard,
that red is the named blocker. ML chose the **"port + parallel jail-prep, no bridge"** path: do the blocked
work (GAP-1 ∧ GAP-2 above) rather than run M1b on a bridge. jcode is build-assist-only, effective now; no
interim jcode NEop seats.

This decision was made on **what the runtime code does** (`pi-neop-runtime` traced at file:line), not on the
authority of either the canon or the plan — so it is not re-litigable by re-reading either document.

## Verification — DONE (2026-06-30)

- [x] Hermes runtime repo named by ML (`mansi118/pi-neop-runtime`) and traced.
- [x] Runs a real prompt→LLM→tool→observe loop — **child-1 GREEN** (`model.ts:123-142`, `supervisor.ts`,
      `@earendil-works/pi-agent-core`).
- [x] Satisfies the NEOS spine contract? — **child-2 RED** (`memory.ts:23`: live PALACE unwired; no `/mcp`
      client/scope/sign/ACL). → GAP-1.
- [x] Containerizable under the proven egress-jail spec? — **child-3 AMBER** (no jail artifact in-repo;
      feasible, not demonstrated). → GAP-2.
- [x] ML chose the M1b path (option: port + parallel jail-prep); ADR flips PROPOSED → DECIDED; plan banner
      applied.

## Required record-reconciliation (this ADR's consequence on canon)

`runtime/core.py:4-6` and `README.md:13-14` assert *"Production Hermes implements the same contract"* — the
trace shows that is **false today for `/mcp`** (the contract diverged at `memory.ts:23`). The
`neos-implementation` skill's treatment of the Python/Node runtimes as conformance-equivalent must be
softened to **"contract-equivalent by design; `/mcp` conformance RED as of 2026-06-30, tracked as GAP-1."**
(Folded into the same change that lands this ADR.)

## Relationships

- **Supersedes:** NEop-runtime framing in `docs/neop-jcode-adapter-implementation-plan.md`.
- **Independent of:** `ADR-llm.md` — the LLM *provider* (OpenRouter by decision) is orthogonal to the
  *runtime*; either runtime can use either provider.
- **Gates:** M1b / T9 (first real NEop) cannot be specced until this is DECIDED and the runtime is named.
