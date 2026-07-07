# Deploy-topology design pass — where the bridge + wrapper run, and how they reach Synapse, the model, and the palace

> The first place the live half meets reality. Supersedes/extends `nc-channels-placement.md` (#84), which
> predated the Hermes **seat wrapper** — the topology now has THREE runtime components, not one, and the
> binding constraint is **spine-VPC egress**, verified from the terraform below. This is a DESIGN pass:
> it surfaces the decisions and what must be box-verified BEFORE any `terraform apply`. No apply here.

## Components (post-seam) and the one hard constraint
| Component | What | Where it must be |
|---|---|---|
| **Synapse** | production homeserver `matrix.neuraledge.in` | EC2, **default VPC 172.31, public** (fixed, exists) |
| **nc-channels bridge** | Python AS: receives txns, forwards to wrapper, reply_send | *placement TBD — this doc* |
| **Hermes seat wrapper** | Node: `POST /seat/turn` → classify → reply/task → palace + model | **spine VPC** (see below) |
| **CORTEX-PALACE `/mcp`** | Convex, ranked memory | spine VPC `10.40`, **internal only** (Cloud Map, exists) |

**The hard constraint:** the wrapper calls the palace `/mcp`, which is **internal to the spine VPC**. So the
**wrapper must run in the spine VPC** (or peer into it). That's fixed. Everything else is placement around it.

## Verified egress reality (from `infra/terraform/`, not assumed)
- **`enable_nat_gateway=false`** — the spine VPC is **no-NAT: private tasks have NO internet egress.**
- `endpoints.tf` gives private tasks AWS services WITHOUT NAT via PrivateLink: `ecr.api/dkr`, `logs`,
  `secretsmanager`, and **`bedrock-runtime`** (private DNS override — the path Convex's Titan embedder uses).
- **`endpoints.tf:8` (load-bearing):** *"Model/embedder egress is deferred, so the spine needs no other
  internet."* ⇒ **the model-GENERATION path has no egress in the no-NAT spine today.**
- `ecs.tf:40` nonetheless wires the runtime LLM to **OpenRouter** (`OPENROUTER_API_KEY`), which is **public
  internet** → **it cannot be reached from the no-NAT spine.** This is the central unresolved tension.

## The hops each component needs, and whether the network exists
| Hop | From → To | Network need | Exists in no-NAT spine? |
|---|---|---|---|
| inbound txns | Synapse (public) → **bridge** `/transactions` | bridge reachable from public Synapse | ❌ needs a public ingress to the bridge |
| reply | **bridge** → Synapse CS-API (public) | egress to the public internet | ❌ no-NAT → **blocked** |
| forward | **bridge** → **wrapper** `/seat/turn` | bridge reaches wrapper | depends on placement |
| memory | **wrapper** → palace `/mcp` (internal) | in-VPC | ✅ (wrapper in spine) |
| **model** | **wrapper** → LLM | egress (OpenRouter=internet) OR in-VPC (Bedrock) | ❌ for OpenRouter; ✅ for Bedrock-via-PrivateLink |

**Two egress problems fall out:** (1) the bridge↔public-Synapse hops, and (2) the wrapper→model hop. Both are
"no internet in the spine." They drive the two decisions below.

## Decision 1 — bridge placement (this resolves the Synapse hops)
- **Option A — bridge in the spine VPC** (the #84 shape, extended): inbound needs a **public token-gated
  HTTPS ALB** → bridge AS port; reply needs **egress to public Synapse** → requires **NAT** (or peering to
  the default-VPC Synapse). Two public-facing/egress concerns just for Synapse.
- **Option B — bridge co-located on the `matrix-server` box** (default VPC, next to Synapse — the Bar 1a
  shape): **both Synapse hops become localhost** (inbound `/transactions` = localhost; reply CS-API =
  localhost/public, trivially reachable). **No NAT, no public ALB for Synapse.** The bridge is a thin
  transport (no NEop, no palace, no model, no secrets beyond AS + forward tokens), so it not being in the
  GAP-2 jail is acceptable — the NEop-executing component (the wrapper) IS jailed in the spine. The single
  cross-boundary hop becomes **bridge → wrapper**, which is **authenticated** (`forward_token`, constant-time)
  and one-directional.
- **⇒ Recommend Option B.** It eliminates both Synapse egress problems (localhost), keeps the jailed component
  in the jail, and reduces the whole cross-VPC question to ONE authenticated hop. **Reconciliation note:**
  `wiring-map.md` assumed a Bar-1a→Bar-2 *relocation* of the bridge into the spine VPC; this egress analysis
  says **keep the bridge on the matrix box** — the relocation was the wrong instinct once the no-NAT reply
  hop is accounted for. Update the wiring-map when this lands.

Under Option B, the one hop to solve is **matrix-box bridge → spine-VPC wrapper.** Two ways: a **public
token-gated HTTPS ALB** in front of the wrapper (bounded by the constant-time `FORWARD_TOKEN` + scope-from-env
we built), or **VPC peering** matrix↔spine scoped by SG (bridge SG → wrapper port only). Recommend the ALB
unless you want the peering lockdown — same tradeoff #84 reached, now on the wrapper's inbound instead.

## Decision 2 — the wrapper's model egress (the OpenRouter-vs-no-NAT tension)
The wrapper must reach a model. In the no-NAT spine:
- **Option M1 — `enable_nat_gateway=true`.** OpenRouter works (keeps `ADR-llm` D2), no runtime code change.
  Cost: a NAT + an **internet egress surface on the jailed spine** (weakens the "no internet" posture the
  endpoints design deliberately holds; the GAP-2 container jail still confines the process, but the VPC gains
  egress).
- **Option M2 — Bedrock in-VPC via the existing `bedrock-runtime` PrivateLink.** No NAT, no internet — the
  spine stays sealed, reusing the **proven** Bedrock path (Nova generative + Titan embeddings, T0-verified).
  Cost: **`pi-neop-runtime`'s `ModelBroker` has no Bedrock provider today** (`model.ts` `PROVIDER_KEY_ENV` =
  `{anthropic, openrouter}` only) — M2 needs a `bedrock` provider added to the broker (real, bounded code work).
- **⇒ Lean M2 for architecture** (keeps the spine internet-free, matches the jail posture, reuses proven
  Bedrock), **but it is gated on ModelBroker Bedrock support.** M1 is the faster path if you accept NAT.
  **This is the key decision of the pass — resolve it before any apply**, because it changes both the TF
  (`enable_nat_gateway`) and possibly the runtime code.

## What this implies for the terraform (authored, HELD, box-verified before apply)
- **Wrapper service** (NEW): ECS Fargate task in the spine VPC private subnets, image = `pi-neop-runtime`
  (the GAP-2 jail image), Cloud Map `seat-wrapper.<ns>.local:8090`, secrets `FORWARD_TOKEN` + palace scope
  (`PALACE_ID`/`NEOP_ID`/`PALACE_MCP_URL`) + model creds (per Decision 2) + `NEOP_T9_ACK` (set only at T9).
- **Wrapper inbound** (Option B + ALB): a public HTTPS ALB + ACM cert → wrapper `:8090`, token-gated.
- **`nc-channels.tf`** (held): under Option B it is **NOT a spine-VPC Fargate service** — the bridge runs on
  the matrix box. Retire the spine-Fargate bridge assumption; the held file's Synapse-SG coupling is moot.
- **Decision 2 → `enable_nat_gateway`**: `true` (M1) or stays `false` (M2 + broker work).
- **Images to build+push to ECR:** `pi-neop-runtime` (GAP-2 jail) — pullable in-VPC via the ECR endpoint.

## Box-verify BEFORE any apply (do not assume)
1. **The spine VPC's real egress** — confirm `enable_nat_gateway` in the live state, and whether the running
   `runtime` task actually reaches a model today (does the OpenRouter path work live, or has it never run?).
   This tells you if Decision 2 is already forced.
2. **Does a public-subnet/ALB path exist** in the spine VPC for the wrapper inbound (Option B) — the "ALB 503
   by design" note implies an ALB exists but with no target; confirm.
3. **Synapse's default-VPC reachability** if you ever consider peering (Decision 1 Option A fallback).

## READ RESULTS — reality resolves Decision 2 (2026-07-07, live AWS read, no apply)
Ran the low-risk read before deciding. It collapsed the fork — and surfaced a finding of the same class as
`core.py`-raises-on-live.

1. **No-NAT is REAL, TF is accurate (not stale).** `describe-nat-gateways` = `[]` (none in the account). The
   runtime task (`neos-dogfood-runtime`) runs in subnets `subnet-0ed33ab…` + `subnet-025eb00af…` — **both
   private, no `0.0.0.0/0` route** — with **`assignPublicIp: DISABLED`**. ⇒ **The runtime has ZERO internet
   egress.** OpenRouter (internet) is genuinely unreachable; the TF and reality agree.

2. **THE FINDING — the runtime has NEVER reached a model or processed a turn.** Its logs, repeated every
   boot, say verbatim:
   - `[runtime] boot self-check passed; idle — transport arrives in S0.3 (nc-channels)`
   - `[selfcheck] WARN missing recommended classifier fallback: set one of OPENROUTER_API_KEY (running degraded)`
   So: **`OPENROUTER_API_KEY` is not even set** ("missing… running degraded"), the runtime **boots,
   self-checks, and sits IDLE** waiting for transport that nothing wired until our seam. **Zero turns, zero
   model calls, zero egress errors** (nothing to error — it never tried). ⇒ **The "convex/runtime/bridge
   healthy 1/1" banked all arc = container-healthy + IDLE, NOT functionally working.** Running ≠
   has-reached-a-model, confirmed at the deepest layer. `endpoints.tf`'s "model/embedder egress is deferred"
   is literally true: **the live-model path was never built** — not a regression, an always-future item now
   coming due. This is the first time a real model path gets built.

3. **Bedrock GENERATION is NOT invokable by the task (corrected — I over-read the first probe).** A test
   invoke of `apac.amazon.nova-lite-v1:0` returned `"OK"` — BUT that was as the dev-box IAM user
   `mansi-synlex` against the **PUBLIC** Bedrock endpoint, NOT the task role in-VPC. It proves account/user
   generation access exists; it does **not** prove the operative path. The operative path is BLOCKED:
   **the task's Bedrock IAM policy is scoped to `amazon.titan-embed-text-v2:0` ONLY** (`iam.tf:50-56`,
   `sid=BedrockInvokeEmbeddings`) — the runtime/wrapper task **cannot invoke any generation model.** And the
   in-VPC `bedrock-runtime` PrivateLink generation reachability is unverified. `responds ≠ the-operative-thing`:
   "my user invoked Nova via public Bedrock" is NOT "the task can invoke Nova in-VPC."

### ⇒ Decision 2 is NOT resolved — BOTH model paths are currently blocked (the fork changed shape)
This is the "if Bedrock generation is also blocked, the fork is genuinely different" case. Today, the wrapper
has **no working model path**:
- **OpenRouter** — unreachable (no-NAT); enabling it needs `enable_nat_gateway=true` = an internet hole in the
  sealed spine (fights GAP-2 + `endpoints.tf`).
- **Bedrock generation** — the task IAM forbids it (embed-only), AND in-VPC generation reachability is unproven.

So the model path is genuinely **unbuilt AND blocked both ways.** The real options, pending what's actually
grantable on this account:
- **(i) Enable Bedrock generation for the task** — widen the task IAM to `InvokeModel` on a generation model
  (Nova inference profile), confirm the account model-access grant covers it, AND box-verify the in-VPC
  endpoint routes generation. If all three hold, this keeps the spine sealed (preferred). **Blocked if** any
  of IAM/account-grant/in-VPC-generation is not available — which the operator (ML) has indicated it is not.
- **(ii) NAT for OpenRouter** — internet egress on the jailed spine (posture cost).
- **(iii) A different in-VPC-reachable model host.**
**This is an ML/operator decision + capability question, not one the design can settle alone.** The read
proved the account *can* generate (my user did), but the *task* cannot as configured, and ML says Bedrock is
not invokable for this path — so treat (i) as unavailable unless ML confirms the IAM/access can be granted.

## Net
The wrapper is pinned to the spine VPC (internal palace). The rest is two decisions driven by the no-NAT
constraint: **(1) bridge on the matrix box** (Synapse=localhost, one authed hop to the wrapper) — recommended
over relocating it into the spine; **(2) the wrapper's model** — Bedrock-in-VPC (sealed spine, needs a broker
Bedrock provider) vs OpenRouter (needs NAT). Resolve Decision 2, box-verify the three items, then author the
wrapper TF + retarget the bridge deploy. This is the design; the apply is a separate, ML-gated box session.
