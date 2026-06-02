# NeuralChat — End-to-End System Design · **Section 1 of 3**
## Foundation — Substrate, the Hermes/Pi-Agent Runtime & Architecture

| | |
|---|---|
| **Doc ID** | NE-TSD-NC-V2 · S1 |
| **Derives from** | NE-TRD-NC-V0 (locked) + NE-TSD-NC-V1 + codex-hardened blueprint |
| **Owner** | Mansi Gambhir (VP AI Research) |
| **Runtime** | **Hermes** runtime host · **Pi-agents (π-agents)** as the execution unit · Convex · Matrix Synapse |
| **Region** | AWS `ap-south-1` (Mumbai) — cloud-only V1 |
| **Reads with** | S2 (Intelligence: components, memory, twin) · S3 (Runtime & Ops: flows, security, build) |

> **Section 1 scope.** Everything below the user-visible surface: what NeuralChat is, where it sits in NEOS, the runtime model (Hermes hosts Pi-agents), the locked layered architecture and ten-service decomposition, the deployment topology, and the multi-tenant data model. Components and flows are in S2/S3. **The substrate must be correct before any user-visible surface is built.**

---

## 1.0 Runtime naming — read this first

The runtime is referred to throughout all three sections as the **Hermes/Pi-agent runtime**. The terms are precise and not interchangeable:

| Term | What it is | Lifetime |
|---|---|---|
| **Hermes** | The agent **runtime host** — process supervisor, session scheduler, model/tool broker, filesystem-watch loader. Formerly *OpenClaw*; the names are **unified — one and the same**. | Long-lived service (`nc-neop-runtime`, `nc-orchestrator`) |
| **Pi-agent (π-agent)** | The **unit of execution**. A NEop *definition* (a folder of Markdown) is instantiated by Hermes as a **Pi-agent** — a running, tenant-scoped session that owns the plan→execute→verify loop. | Per NEop run (a session) |
| **Pi-subagent** | A Pi-agent spawns three **Pi-subagents** — `planner`, `executor`, `verifier` — each a bounded model call with its own MD prompt. | Per phase, within a run |
| **NEop** | The **definition**: `agents/<name>/*.md` + JSON sidecars. Static, version-controlled. Becomes a Pi-agent only when Hermes loads and runs it. | Indefinite (git) |

```mermaid
flowchart LR
    subgraph DEF["NEop definition (static · git)"]
        MD["agents/recon/*.md<br/>planner.md · executor.md · verifier.md<br/>tools.json · capabilities.json · metrics.json"]
    end
    subgraph HERMES["Hermes runtime host (nc-neop-runtime)"]
        LOADER["Loader<br/>resolution tree + fs-watch"]
        SCHED["Session scheduler<br/>concurrency caps · session affinity"]
    end
    subgraph RUN["Pi-agent run (a session · tenant-scoped)"]
        PA["Pi-agent<br/>owns plan→execute→verify"]
        PLN["Pi-subagent: planner"]
        EXE["Pi-subagent: executor"]
        VER["Pi-subagent: verifier"]
        PA --> PLN --> EXE --> VER
    end
    MD --> LOADER --> SCHED --> PA
```

**Rule of thumb for the rest of the spec:** wherever V1 said "NEop runtime" read "Hermes"; wherever it said "a NEop run" read "a Pi-agent session"; the planner/executor/verifier are Pi-subagents.

---

## 1.1 What NeuralChat is, and where it sits in NEOS

NeuralChat is an **execution layer for AI-based knowledge work** and the **only human-facing layer of NEOS** — NeuralEDGE's 11-layer Digital AI Operating System. Every other NEOS layer is back-of-house; NeuralChat is the front door. Each employee gets one AI assistant that builds a **twin** (`twin.md`, a versioned decision model of how they work) and, over 6–12 months, automates parts of their job.

```mermaid
flowchart TB
    subgraph HUMANS["Humans"]
        U["Employee / Owner"]
    end
    subgraph FRONT["NeuralChat — the front door (human-facing)"]
        UI["Slack-shape UI + twin dashboard"]
        TWIN["Twin layer (twin.md per seat)"]
    end
    subgraph BOH["NEOS — back-of-house (11 layers)"]
        NEOPS["NEops<br/>AI digital employees (MD folders)"]
        NEPS["NePs<br/>self-improvement protocols"]
        PALACE["CORTEX-PALACE<br/>memory substrate"]
        MKT["NEOp Marketplace<br/>(V2 internal catalog)"]
        EVAL["NE-Eval"]
        STUDIO["NE-Model Studio"]
        QB["NE-QuickBuild"]
    end
    U --> UI --> TWIN
    UI --> NEOPS
    NEOPS --> PALACE
    NEOPS --> NEPS
    TWIN --> PALACE
    NEPS -.created by flywheel.-> QB
    NEOPS -.evaluated by.-> EVAL
    NEOPS -.models from.-> STUDIO
    NEOPS -.rented via.-> MKT
```

**NeuralChat's four jobs in the system:** (1) capture the work context NEOS needs to automate; (2) be the trust-and-approval layer before deeper automation; (3) route work to the right NEop; (4) connect personal context to company Context Vaults.

---

## 1.2 The product model — a closed learning loop

The product is **not** a chatbot; it is a closed loop that converts observation into trustworthy automation. The twin predicts; the user acts; the **Decision Shadow** Pi-agent compares; the **Twin Curator** Pi-agent updates; **fidelity** climbs until the twin can be trusted to act.

```mermaid
flowchart LR
    SEED["SEED<br/>Interviewer Pi-agent<br/>≤15-min interview → twin v0"]
    PREDICT["PREDICT<br/>twin.md prepended to<br/>every Pi-agent system prompt"]
    OBSERVE["OBSERVE<br/>Decision Shadow Pi-agent<br/>predicted vs actual"]
    LEARN["LEARN<br/>Twin Curator Pi-agent<br/>≥3 corroborating signals"]
    TRUST["TRUST<br/>rolling 30-day<br/>agreement rate climbs"]
    AUTO["AUTOMATE<br/>trusted twin acts"]
    SEED --> PREDICT --> OBSERVE --> LEARN --> TRUST --> AUTO
    AUTO -.new signals.-> OBSERVE
    LEARN -.versioned write.-> PREDICT
```

**Fidelity is a first-class architectural metric, not marketing.** It is the rolling 30-day agreement rate between twin prediction and user action, computed daily per seat by the Decision Shadow Pi-agent.

| Milestone | Fidelity target | What it unlocks |
|---|---|---|
| Day 0 (seed) | n/a (`maturity: seed`) | Twin prepended but advisory only |
| Day 90 | **≥ 0.65** | Alpha acceptance bar; twin trusted for low-risk inline acts |
| Day 180 | **≥ 0.75** | Paying-tenant bar; broader delegation |

The **conservative ramp** (seed at interview, climb only on corroborated signals) is simultaneously the headline product metric *and* the top sales risk — so it is engineered, measured, and surfaced rather than asserted.

---

## 1.3 Locked layered architecture (TRD §3.1)

Every inbound message walks the **same vertical path**. Three substrates fan out beneath the Hermes runtime. The shape is **locked** — components plug into it, they don't reshape it.

```mermaid
flowchart TB
    UI["UI LAYER — Slack-shape web app · channels · DMs · threads · twin dashboard"]
    CA["CHANNEL ADAPTERS — Matrix (primary) · Telegram · Slack · WhatsApp · Email"]
    GW["GATEWAY (Hermes-ext) — authN/Z · tenant resolution · rate limit · approval mediation"]
    ORC["ORCHESTRATOR — Coordinator Pi-agent · intent classification · dispatch · multi-NEop join"]
    RT["HERMES RUNTIME — hosts Pi-agents · planner → executor → verifier · per-tenant scoped"]
    UI --> CA --> GW --> ORC --> RT
    RT --> TOOL["Tool Bus<br/>MCP servers · Skills"]
    RT --> PAL["CORTEX-PALACE<br/>STM / LTM / Vault"]
    RT --> ACP["ACP Router<br/>envelope · signature · audit"]
    TOOL --> DATA
    PAL --> DATA
    ACP --> DATA
    DATA["DATA LAYER — Redis · Convex · FalkorDB · ClickHouse · S3"]
```

Request path runs **top-to-bottom**; the three substrates (Tool Bus, CORTEX-PALACE, ACP) fan out from the runtime; the data layer sits along the base. Detailed per-component specs are in **S2**.

---

## 1.4 Ten-service decomposition (TRD §3.2)

Internal transport: **HTTP/2 (gRPC where ergonomic)**, **NATS** for event fanout. Every call carries a **W3C trace context** (`traceparent`) and an **`X-NC-Tenant-Id`** header — no exceptions.

```mermaid
flowchart TB
    subgraph EDGE["Public edge (ALB)"]
        WEB["nc-web · React/TanStack<br/>Slack-shape client + dashboard"]
        GW["nc-gateway · Node/Fastify<br/>auth · tenant · rate-limit · approvals · WS fanout"]
    end
    subgraph CORE["Core runtime (private)"]
        ORC["nc-orchestrator · Node/Hermes<br/>Coordinator Pi-agent · intent · lifecycle"]
        RT["nc-neop-runtime · Node/Hermes<br/>hosts Pi-agent sessions"]
        ACP["nc-acp · Node/Fastify<br/>ACP router · sig verify · audit emit"]
        CH["nc-channels · Node<br/>Matrix/Telegram/Slack adapters"]
    end
    subgraph MEM["Memory + data plane (private)"]
        PAL["nc-palace · Python/FastAPI<br/>Convex+FalkorDB · embed · retrieve"]
        AUD["nc-audit · Python/ClickHouse<br/>append-only ingest + query"]
        EV["nc-eval · Python<br/>scheduled NeP eval runner"]
    end
    ADM["nc-admin · React/TanStack<br/>tenant provisioning · billing · audit UI"]

    WEB --> GW
    CH --> GW
    GW --> ORC --> RT
    RT --> PAL
    RT --> ACP
    ACP --> AUD
    GW --> AUD
    PAL --> AUD
    EV --> PAL
    ADM --> GW
```

| Service | Stack | Owns | Stateful? |
|---|---|---|---|
| `nc-gateway` | Node · Fastify | Auth, tenant resolution, rate limit, approvals, WS fanout | No (Fargate) |
| `nc-orchestrator` | Node · **Hermes** | Coordinator Pi-agent, intent routing, NEop lifecycle | No (Fargate) |
| `nc-neop-runtime` | Node · **Hermes** | Hosts **Pi-agent sessions**; model & tool calls | **Yes** — session affinity (EC2) |
| `nc-palace` | Python · FastAPI | Memory — Convex + FalkorDB, embedding, retrieval | No (Fargate) |
| `nc-acp` | Node · Fastify | ACP router, signature verification, audit emitter | No (Fargate) |
| `nc-channels` | Node · adapters | Matrix / Telegram / Slack adapters | No (Fargate) |
| `nc-web` | React · TanStack Start | Slack-shape client + dashboard | No (Fargate) |
| `nc-admin` | React · TanStack Start | Tenant provisioning, billing, audit UI | No (Fargate) |
| `nc-audit` | Python · ClickHouse | Append-only audit ingestion + query | No (Fargate) |
| `nc-eval` | Python | Scheduled NeP eval runner | No (Fargate) |

**Why `nc-neop-runtime` is the one stateful service:** a Pi-agent session is long-lived (a NEop run can be ≤30s synchronous-feeling or minutes for deep work), holds an in-flight plan DAG + STM working set, and must survive the approval round-trip without losing state. It gets EC2 session affinity; everything else is stateless on Fargate.

---

## 1.5 Deployment topology — AWS `ap-south-1` (TRD §3.3)

Cloud-only, **Mumbai region** for V1 (DPDP data residency). A public ALB exposes **only `nc-gateway` and `nc-web`** — everything else lives in private subnets. Multi-region is V2.

```mermaid
flowchart TB
    INET["Internet"]
    INET --> ALB["Public ALB<br/>(only gateway + web exposed)"]
    subgraph PUB["Public subnets"]
        ALB --> NCWEB["nc-web (Fargate)"]
        ALB --> NCGW["nc-gateway (Fargate)"]
    end
    subgraph PRIV["Private subnets"]
        NCGW --> FARGATE["Stateless services<br/>orchestrator · acp · channels · palace · audit · eval · admin (Fargate)"]
        FARGATE --> EC2RT["nc-neop-runtime<br/>EC2 m7i.2xlarge · session affinity"]
        EC2RT --> FALKOR["FalkorDB on EC2<br/>namespace per tenant"]
        EC2RT --> CLICK["ClickHouse on EC2<br/>partitioned (tenant_id, day)"]
        FARGATE --> CONVEX["Convex<br/>system of record"]
        FARGATE --> REDIS["Redis · ElastiCache<br/>session cache · rate limits · idempotency"]
        FARGATE --> S3["S3<br/>artifacts >1 MB"]
        subgraph SYN["Matrix layer"]
            SYNAPSE["Synapse homeserver<br/>one container per tenant"]
            PG["Shared Postgres<br/>DB partitioned per tenant"]
            SYNAPSE --> PG
        end
        NCGW --> SYNAPSE
    end
```

| Concern | Decision |
|---|---|
| Compute (stateless) | ECS Fargate — all stateless services |
| Compute (stateful) | EC2 `m7i.2xlarge` — `nc-neop-runtime` (Pi-agent session affinity) |
| Networking | VPC — public ALB fronts `nc-gateway` + `nc-web` only; rest private |
| System of record | Convex — config, twins, plans, sessions |
| Graph | FalkorDB on EC2 — namespace per tenant |
| Audit | ClickHouse on EC2 — partitioned `(tenant_id, day)` |
| Artifacts >1 MB | S3 |
| Cache / rate limit / idempotency | Redis · ElastiCache |
| Channels | One Synapse container **per tenant**, shared Postgres, DB partitioned per tenant |

**Provisioning a new tenant is a Terraform-automated unit:** Synapse container + Vault namespace + audit partition + per-tenant keys, applied as one module.

---

## 1.6 Multi-tenancy — the isolation backbone (TRD §1.5, §5)

**`tenant_id` is the universal access key — no code path issues a read or write without it.** The hierarchy is strict; isolation is enforced **independently at four layers** (full ACL in S3 §3.2).

```mermaid
flowchart TB
    T["TENANT — one company contract<br/>= 1 Matrix homeserver + 1 Vault + N seats<br/>+ own FalkorDB namespace + own audit partition"]
    T --> S1["SEAT — one employee<br/>= twin + personal LTM (personal_seat)<br/>+ NEop bindings + STM session cache"]
    T --> S2["SEAT ..."]
    S1 --> TW["TWIN — twin.md<br/>decision model · versioned on every change"]
    S1 --> BIND["NEop bindings<br/>which Pi-agents this seat can run"]
    S1 --> STM["STM session cache (Redis)"]
```

| Property | V1 | V2 |
|---|---|---|
| Seats / tenant | ≤ 20 | up to 200 |
| Concurrent Pi-agent runs / tenant | 16 | 50 |

**Isolation invariant (NFR-10):** No Pi-agent in tenant A can read tenant B data. Enforced at the gateway **AND** the PALACE client **AND** the ACP router — defense in depth, no single layer trusted.

---

## 1.7 Data model — three stores, one responsibility each (TRD §5)

Convex is the **system of record**; FalkorDB owns the **graph**; ClickHouse owns **audit volume**.

### 1.7.1 Convex — system of record (15 collections)

```mermaid
erDiagram
    TENANTS ||--o{ SEATS : has
    SEATS ||--|| TWINS : owns
    TWINS ||--o{ TWIN_DIFFS : versions
    SEATS ||--o{ SESSIONS : opens
    SESSIONS ||--o{ MEMORIES : consolidates
    TENANTS ||--o{ VAULT : holds
    SEATS ||--o{ PLANS : runs
    PLANS ||--o{ TASKS : contains
    TASKS ||--o{ APPROVALS : gated_by
    SEATS ||--o{ ACP_ENVELOPES : sends
    SEATS ||--o{ SIGNALS : emits
    SEATS ||--o{ DECISIONS_SHADOW : shadowed_by
    TENANTS ||--o{ TENANT_CHANNELS : binds
    TENANTS ||--o{ POLICIES : governs

    TENANTS {
        string tenant_id PK
        string name
        string synapse_homeserver
        string vault_namespace
    }
    SEATS {
        string seat_id PK
        string tenant_id FK
        string role "owner|admin|member"
        string ltm_namespace "personal_seat"
    }
    TWINS {
        string twin_id PK "tenant:seat"
        int version
        float fidelity_score
        string maturity "seed|growing|mature|drifted"
    }
    TWIN_DIFFS {
        string diff_id PK
        string twin_id FK
        int from_version
        int to_version
        blob compressed_diff
    }
    SIGNALS {
        string signal_id PK
        string seat_id FK
        string kind "fidelity|override|observation"
        json payload
    }
    DECISIONS_SHADOW {
        string shadow_id PK
        string seat_id FK
        string decision_class "communicative|selective|generative"
        json predicted
        json actual
        bool agreed
    }
```

Full collection list: `tenants · seats · twins · twin_diffs · sessions · memories · vault_<tenant> · plans · tasks · approvals · acp_envelopes · signals · decisions_shadow · tenant_channels · policies`.

### 1.7.2 FalkorDB — graph (Graphiti temporal layer)

- **Per tenant** `vault_<tenant>` — org knowledge + hierarchy graph.
- **Per seat** `personal_<seat>` — relationships, decisions, project graph.
- **Graphiti** adds temporal edges + multi-hop Cypher; retrieval detail in **S2 §2.5**.

### 1.7.3 ClickHouse — audit volume

- `audit_events` — append-only, partitioned `(tenant_id, day)`.
- `neop_traces` — flattened OTel for cost/perf analysis.
- `acp_envelopes` migrate here in V2 when volume warrants.

### 1.7.4 Retention & lifecycle (TRD §5.4)

| Data type | Retention | Reason |
|---|---|---|
| Active twin | Indefinite | Live operating data |
| Twin diff history | Indefinite · compressed | Rollback + audit |
| STM — sessions | 30d hot → consolidated | Performance |
| LTM | Until seat deletion | Twin learning |
| Vault | Until tenant offboard | Org memory |
| Audit log | **7 years** | DPDP / SOX-ready |
| Decision shadow | 90 days | 30d window + analysis |
| ACP envelopes | 90d hot → S3 archive | Volume |

> **Deletion-routing (V1+ blocker).** An audit-relevant event can live in four stores — local `audit.jsonl`, the Cortex audit wing, Matrix room history, the Companion Channels feed. A deletion request must reach **all four** atomically, with CI restore-tests. Tracked as a gating item; design lands in S3.

---

### Section 1 → Section 2 handoff

S1 fixed the substrate: the Hermes/Pi-agent runtime model, the locked layering, ten services, the deployment, and the multi-tenant data model. **S2 (Intelligence)** specifies each component in depth — the gateway trust seam, channel adapters, the orchestrator's intent classifier, the Hermes/Pi plan-execute-verify engine, the CORTEX-PALACE retrieval fusion, the twin layer and its maturity state machine, the ACP router, and the six meta-NEops realized as Pi-agents.
