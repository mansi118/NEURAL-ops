---
name: neos-implementation
description: >
  Canonical engineering ground-truth for the NEOS platform (NeuralEDGE Operating System) and
  its human-facing front door, NeuralChat. Use whenever a task touches HOW the system works
  under the hood: the 11-layer architecture and nc-* services, the Hermes/OpenClaw/Pi runtime,
  the CORTEX-PALACE memory substrate (Convex + FalkorDB + Voyage), the digital-twin/fidelity
  model, the 4-layer ACL and ACP envelopes, NEop anatomy and the NeP self-improvement loop, the
  NEOP Marketplace, the AWS ap-south-1 topology, the repos (Mempalace_NEOS, NEURAL-ops), or
  current build/deploy state. Triggers: "how does CORTEX-PALACE store the twin", "what's the
  ACL design", "what's blocking the dogfish deploy", "what NEops exist", "the tenant/seat/twin
  model" — any architecture/memory/security/runtime/build question about NEOS/NeuralChat.
  REFERENCE skill, NOT a builder: NEop Blueprints → neop-spec; NEOS Notion UI → neos-frontend;
  chat UI → neural-chat-ui; client docs → neuraledge-doc; brand → neuraledge-brand.
---

# NEOS Implementation — Engineering Ground Truth

This skill is the single source of truth for how the NEOS platform and NeuralChat are
designed and built. It exists so any session (or Claude Code agent) can load full,
consistent system context instead of reconstructing it from scattered chats each time.

**What it is NOT:** a builder skill. It carries no opinions about UI styling, doc templates,
or blueprint authoring — those live in `neos-frontend`, `neural-chat-ui`, `neuraledge-doc`,
`neuraledge-brand`, and `neop-spec`. This skill answers "how does it work / what's the
current state," and hands off to those skills for "now build X."

> **Freshness note.** Architecture (layers, runtime, memory, ACL, ACP) is stable and changes
> rarely. `references/build-state.md` is **time-sensitive** — it reflects the state as of
> mid-2026 and must be treated as a snapshot, not eternal truth. When build questions are
> live, confirm against the repos / latest session before acting on the snapshot.

> **Stored-copy note (2026-06-26).** This SKILL.md was checked into the NEURAL-ops repo as the
> canonical store. The `references/*.md` sub-files are NOT yet populated here — until they are,
> use the "Source provenance" chats below for deeper detail, and confirm live build state
> against the repos + the deployment runbook (`docs/deployment/dogfood-spine-runbook.md`) and
> the production-readiness ledger (`docs/production-readiness.md`).

---

## The one-paragraph model

**NEOS** is an 11-layer AI Digital Operating System a business runs on. **NeuralChat** is its
*only* human-facing layer — a digital-twin platform where every employee gets a personal twin
(a versioned `twin.md`) and **NEops** (digital employees, each a folder of Markdown) are the
limbs the twin dispatches work to. **NePs** (NeuralEDGE Protocols) are the self-improving
contracts that make NEops get better over time; they and the NEops are sold/rented through the
**NEOP Marketplace**. Everything runs on the **Hermes** runtime (≡ OpenClaw — unified as one
and the same; built transitively on **Pi**) and remembers through **CORTEX-PALACE** (Convex
system-of-record + FalkorDB advisory graph + Graphiti, Voyage embeddings).

```
                    ┌─────────────── NEOS (11-layer Digital AI OS) ───────────────┐
   human ─────────► │  NeuralChat (the ONLY human-facing layer / front door)       │
                    │     twin.md  ·  fidelity  ·  Slack-shape UI  ·  channels      │
                    │        │ dispatches                                           │
                    │        ▼                                                      │
                    │  NEops (digital employees)  ◄──improved by──  NeP contracts   │
                    │        │                                          ▲           │
                    │        │ runs on                         sold via │           │
                    │        ▼                                  NEOP Marketplace    │
                    │  Hermes runtime (≡ OpenClaw, on Pi)                            │
                    │        │ remembers through                                    │
                    │        ▼                                                      │
                    │  CORTEX-PALACE  (Convex SoT + FalkorDB graph + Voyage embeds)  │
                    └───────────────────────────────────────────────────────────────┘
```

---

## Canonical vocabulary (do not drift)

| Term | Meaning |
|---|---|
| **NEOS** | NeuralEDGE Operating System — the 11-layer multi-tenant platform a business runs on. |
| **NeuralChat** | The single human-facing layer of NEOS. A digital-twin platform, **not** "Slack with AI agents." |
| **NEop** | A digital employee = a folder of Markdown (SOUL/PROTOCOLS/TOOLS + `openclaw.json`) running as a provisioned Hermes agent instance. |
| **NeP** | NeuralEDGE Protocol — a Skill.md-like file with embedded metrics that self-optimizes; a NEop's self-improvement contract. |
| **NEOP Marketplace** | Where businesses buy NePs and rent NEops. 60/40 revenue share on client custom NEops. |
| **Hermes** | The agent runtime. **Treated as one and the same as OpenClaw.** Built transitively on Pi. |
| **Pi** | `pi-mono` (Mario Zechner) — the foundational TS agent toolkit under Hermes/OpenClaw. |
| **CORTEX-PALACE** | The 3-tier memory substrate (Memory → Cortex → Context Vault) over Convex + FalkorDB + Graphiti, Voyage embeddings. |
| **MemPalace / Mempalace_NEOS** | The Convex/TypeScript memory backend repo (outward-facing). |
| **NEURAL-ops** | The Python agent spine + broker repo. |
| **twin.md** | A versioned, schema-typed file modelling one employee's decision style. The unit of value. |
| **Fidelity** | Rolling 30-day rate at which the twin's prediction agrees with the employee's actual decision. The unit of trust. |
| **Tenant / Seat / Twin** | Tenant = one company contract. Seat = one employee instance. Twin = one seat's `twin.md`. |
| **ACP** | Agent Communication Protocol — Ed25519-signed message envelope; envelope-compatible with IBM ACP / Google A2A. |
| **4-layer ACL** | Convex SoT → FalkorDB signed headers → MCP tool-wrapper → Python SDK call-site. Defense in depth. |
| **STM / LTM / Vault** | Short-term (session) / long-term (per-seat) / Company Context Vault (per-tenant). |

---

## How to navigate this skill

Read the reference file that matches the question. Each is self-contained. Don't read all of
them for a narrow question — pick the one(s) that fit. (Sub-files pending — see stored-copy note.)

| If the question is about… | Read |
|---|---|
| The 11 layers, the locked layered request path, the 10-service decomposition, AWS topology, the Hermes/OpenClaw/Pi runtime stack, scale envelope | `references/architecture.md` |
| Memory: the 3 tiers, the palace/wing/hall structure, the `palace_search`/`palace_remember`/`palace_get_closet` access API, twin-storage invariant, retrieval flow, MAGMA | `references/cortex-palace.md` |
| The product model: twin → shadow → fidelity loop, the 6 meta-NEops, scope V1/V2, pricing, success criteria (AC-1…AC-10), the canonical message + twin.md schemas | `references/neuralchat-twin.md` |
| NEop anatomy, the named-NEop roster, the NeP self-improvement loop, NeP types, NEOP Marketplace economics, the OpenClaw capability mapping | `references/neops-and-neps.md` |
| Security: the 4-layer ACL in detail, ACP envelopes + Ed25519, tenant isolation, the twin seat-scope foot-gun, secrets posture | `references/acl-acp-security.md` |
| Current build state: repos, commits, what's green, what's blocked (dogfish), the jcode adapter, LLM swap (GLM-5.2/OpenRouter), Bedrock block, security action items | `references/build-state.md` |

---

## Hard invariants (violating any of these is a bug, not a choice)

These are load-bearing decisions that were reached deliberately. Preserve them.

1. **Hermes ≡ OpenClaw.** One runtime, two names. Don't reintroduce them as separate systems.
2. **The twin is by-id-only.** `twin.md` lives in a dedicated Convex `twins` table keyed
   `by_palace_neop` with **zero search/vector indexes** — it must NEVER surface in
   `palace_search`. Storing it as a "closet" (embedded/searchable) violates the core invariant.
3. **`tenant_id` is the universal access key.** No read or write on any code path without it.
4. **Seat scope keys to the *authenticated* `neopId`**, never to a caller-supplied
   `params.neopId` (the `?? ` override path is exploitable — it was found and hardened).
5. **ACL is enforced per-item inside the Cypher query**, not post-retrieval — graph traversal
   must not leak across wings/tenants.
6. **Cortex observes, Vault declares.** Cortex → Vault promotion requires human confirmation.
7. **Fidelity is a 90-day promise, not a day-one claim.** Seeded ~0.40 at Day 0; targets
   ≥0.65 Day 90, ≥0.75 Day 180. Never market it as instant.
8. **The runtime is embedding-agnostic** and gates only on `CONVEX_DEPLOYMENT_URL`.
   Embeddings are computed server-side (Voyage in the live target).
9. **`.convex.site` ≠ `.convex.cloud`.** The HTTP-action (`/mcp`) endpoint is `.convex.site`;
   the deployment/admin endpoint is `.convex.cloud`. Mixing them silently breaks deploys.
10. **Pre-tool / safety hooks fail CLOSED.** Any error denies; never fail open. `jail_enforced`
    must be environment-derived (set by the Docker jail launcher), never caller-asserted.

---

## Brand + identity constants (for any NEOS/NeuralChat artifact)

- Colors: Navy `#132F48`, Teal `#13C5B3`, Ice `#EFF4F9`.
- Fonts: Space Grotesk (display), DM Sans (body), JetBrains Mono (code).
- Legal entity: Synlex Technologies Pvt. Ltd. (Delhi). Brand: NeuralEDGE.
- Spec ownership: **Mansi Gambhir** owns the NeuralChat TSD (NE-TSD-NC-V1/V2). Core team:
  Yatharth Garg / "ML" (Founder/CEO), Dr. Rahul Kashyap (Co-Founder/CTO), Mansi Gambhir
  (VP AI Research); consultants Shivam Singh, Naveen Bisht, Ankit.

---

## Source provenance

This skill was synthesized from the working sessions where each subsystem was designed. When
deeper detail than this skill carries is needed, the originating chats are the next stop:

- Digital-twin platform architecture — `https://claude.ai/chat/879aeaf9-2404-423b-9824-d98478fbb373`
- NeuralChat TRD/TSD deck (NE-TSD-NC-V1, service decomposition, component IDs) — `https://claude.ai/chat/7d330b23-71c4-4e0a-925e-d768985489b1`
- CORTEX-PALACE memory architecture (v2→v4 + retrieval stress test) — `https://claude.ai/chat/ce145780-966f-44a0-aaf2-a256a7cdf6f6`
- Live build session — twins table, ACL, V2 phase plan (commit fc69f34, PR #4) — `https://claude.ai/chat/7a328ea7-6f24-43e6-9c51-9c6349adb51c`
- Historical reference map + dogfish smoke + jcode adapter review — `https://claude.ai/chat/323de7c3-cd0b-4b8d-a0af-32e066bfc515`
- NeP / Marketplace export — `https://claude.ai/chat/571cb7bb-fba8-47bc-b0cc-760d33c59f08`
- OpenClaw hub-and-spoke / capability mapping — `https://claude.ai/chat/b677381e-d08a-4394-8464-3be9fbd056ff`
- Named-NEop roster + tech stack export — `https://claude.ai/chat/14d97e53-6ecb-4814-be54-5df960c75235`
