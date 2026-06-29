# The real path to Day-90 (V1 production acceptance)

**Dated 2026-06-29.** "Production-ready" = the **Day-90 acceptance gate** (≥5 live seats · twin fidelity
≥0.65 · pen-test passed · zero tenant-isolation violations in 30 days). It is inherently live + human —
**never agent-declarable**. This is the consolidated critical path; it supersedes the stale bits of
`production-readiness.md` (2026-06-22) and `activation-timeline.md` after the 2026-06-29 merges.

## Where we are (2026-06-29)
Substrate is **live + proven**, not just offline-built:
- **Spine LIVE on AWS** (ap-south-1, deployed-stack smoke **7/7**), no-NAT (VPC endpoints), ~$100/mo.
- **Embedder LIVE + ranked-retrieval proven** — Bedrock **Titan @1024** via PrivateLink. Done-bar = *ranked
  hits*, not "calls succeed". Gemini-768 parked + NAT-gated. (`docs/decisions/embedder-as-built.md`)
- **D2 resolved + shipped** — runtime LLM = **OpenRouter primary** (classifier `anthropic/claude-haiku-4.5`).
  (`docs/decisions/ADR-llm.md`)
- **jcode adapter OFFLINE-COMPLETE** — T1–T6 built + green (shim, config/isolation-policy, supervisor-core,
  audit/events, safety/pre_tool gate, promoter). Only the **Docker box-exec** remains.
- **Identity/audit/governance spine** built, merged, live-proven (4-layer ACL, all 4 layers emit; approval
  engine has a durable consumer; twin per-user).

**The offline runway is spent.** From here Day-90 moves by **gates + a calendar**, not agent build.

## The critical path — three tracks (only Track C's calendar sets the floor)

### Track A — A NEop executes live (M1b) · the binding engineering gate
| Step | Owner | State |
|---|---|---|
| **jcode T0 go/no-go spike** (jailed proc → shim → live palace round-trip) | ⛔ you | run-book ready (`jcode-t0-spike-runbook.md`); needs the box + jcode binary + model key (OpenRouter on hand). **STOP-and-show.** |
| jcode **box-exec** — `isolation._docker_run` + `supervisor._spawn` + egress firewall | 🔨 on the box | the only remaining adapter stubs; everything they call is built+tested |
| Governance flip (Policy v1) | ⛔+🔨 ~1d | set `approval-policy-v1.md` + env toggles; seam live-proven |
| **T9 — first real NEop** | ⛔ you | explicit STOP-and-ask |

### Track B — A human chats their twin (M2) · ~1–2 wk after M1b
`nc-channels` Matrix adapter (🔨 ~1–2 wk, untraced) → reuse `matrix.neuraledge.in` → talk via a **stock
Element client** (lean first-contact). **`nc-web` is built in parallel** (UI plan) but is **off** the
first-contact path — it must not gate first contact.

### Track C — Twins worth trusting (Day-90) · calendar, non-compressible
Onboard **≥5 seats = Day 0** of the fidelity clock (⛔ you; interviewer seeds twin.md v0) → Decision Shadow
runs, fidelity ~0.40 → **≥0.65 @ Day 90** (calendar) · **30-day zero-isolation-violation window** (mechanism
live-proven) · pen-test · harden · **Day-90 declaration** (⛔ you).

## Day-90 scorecard
| Criterion | Status |
|---|---|
| ≥5 seats, twin v≥5 | ✅ per-user twin + seeded · ⛔ live tenant to accrue versions |
| ≥3 NEops/seat in use | 🔨 P5 fleet re-wrap · ⛔ usage |
| twin fidelity ≥0.65 | ✅ measures the person · 🔨 P4 fidelity clock (live wiring) · calendar outcome |
| chat p95 ≤2s / NEop p95 ≤60s | ⛔ deployed-stack measurement |
| **zero isolation violations 30d** | ✅ mechanism proven (4-layer ACL + audit) · needs the ⛔ 30-day window |
| 6 meta-NEops · dashboard · pen-test | ✅ 4 wrapped · 🔨 dashboard + 2 meta-seams · ⛔ pen-test |

## The date math (why earliest Day-90 ≈ late Oct 2026)
The only lever on Day-90 is starting the 90-day fidelity clock sooner = onboarding ≥5 seats sooner = M2 done
= M1b done = **your jcode T0 greenlight**. Back-calc to hit Day-90 = **D**:
- jcode **T0 greenlit by ~D−118** · Matrix adapter by ~D−100 · M1b by ~D−104 · M2 + onboarding by **D−90**.
- Anchored to a T0 greenlight ~now *and a pass*: M1b ~Jul 11 → M2 ~Jul 25 → onboard ~Jul 28 →
  **earliest Day-90 ≈ 2026-10-26** (Day-180/≥0.75 ≈ 2027-01-24).
- **Every ⛔ slip moves Day-90 one-for-one** — the fidelity calendar can't absorb slack.

## The one variable that matters
Not agent build — it's **your go-cadence on the gated steps, chiefly the jcode T0 go/no-go**, then onboarding.
**The single highest-leverage action this week is clearing jcode T0.** Nothing else on the board moves the date.
Provision the box now: the **EC2 m7i.2xlarge** that runs the prod runtime can run Docker and host the T0 spike,
so the spike isn't itself gated on infra. "Looks like a switch" has been a gated spike twice (the embedder; the
frozen-`core.py` model wall) — treat T0 as a spike, not a flip.

## "Will the agents run fine?" — the honest answer
The execution machinery is built + green and the substrate is live, but **no NEop has executed live yet.**
The last real engineering unknown is the jcode box-exec (Docker isolation + supervisor spawn + egress
firewall); the T0 spike is its proof, and everything it calls is built and tested. Pass T0 and agents
execute live — **gated** (proposing, not committing) until fidelity ramps. That is "running fine" in the only
sense the architecture allows on day one.
