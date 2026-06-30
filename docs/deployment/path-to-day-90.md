# The real path to Day-90 (V1 production acceptance)

**Dated 2026-06-29 · reconciled to `ADR-neop-runtime` 2026-06-30.** "Production-ready" = the **Day-90
acceptance gate** (≥5 live seats · twin fidelity ≥0.65 · pen-test passed · zero tenant-isolation violations
in 30 days). It is inherently live + human — **never agent-declarable**. This is the consolidated critical
path; it supersedes the stale bits of `production-readiness.md` (2026-06-22) and `activation-timeline.md`.

> **RUNTIME RECONCILIATION (2026-06-30, `docs/decisions/ADR-neop-runtime.md` DECIDED).** This doc's earlier
> Track A was framed around **jcode** as the NEop runtime. That was overturned on file:line evidence: the
> NEop runtime is **Hermes** (`pi-neop-runtime`, on `@earendil-works/pi-agent-core` — a real pi-agent loop;
> canon stands). **jcode is NOT a NEop runtime** — it is scoped to the gated **NE-QuickBuild build-assist**
> role. The jcode **T0 strong-GO + T7 strong-pass DID run live (2026-06-29)** — but on the now-demoted jcode
> path, so they **do not satisfy M1b**. M1b moved to the Hermes path, gated on **GAP-1 + GAP-2** (below).

## Where we are (2026-06-30)
Substrate is **live + proven**, not just offline-built:
- **Spine LIVE on AWS** (ap-south-1, deployed-stack smoke **7/7**), no-NAT (VPC endpoints), ~$100/mo.
- **Embedder LIVE + ranked-retrieval proven** — Bedrock **Titan @1024** via PrivateLink. (`embedder-as-built.md`)
- **D2 resolved + shipped** — runtime LLM = **OpenRouter primary** (classifier `anthropic/claude-haiku-4.5`),
  by decision (not a Bedrock block — Bedrock generative works in-VPC). (`ADR-llm.md`)
- **NEop runtime = Hermes** (`pi-neop-runtime`), verified live (real pi-agent loop). jcode demoted to
  QuickBuild build-assist. (`ADR-neop-runtime.md`)
- **Identity/audit/governance spine** built, merged, live-proven (4-layer ACL, all 4 layers emit; approval
  engine has a durable consumer; twin per-user).
- **M1b-blocking work is BUILT** (offline-complete, CI-green, all 3 PRs do-not-merge until their live proofs):
  GAP-1 `pi-neop-runtime#1` · GAP-2 `pi-neop-runtime#2`+`NEURAL-ops#60` · floor fix `Mempalace#29`.

**The offline runway is spent.** From here Day-90 moves by **gates + a calendar**, not agent build. What
remains before M1b is **one authorized box-session** (deploy + two live re-proofs) — not code.

## The critical path — three tracks (only Track C's calendar sets the floor)

### Track A — A NEop executes live (M1b) · the binding engineering gate (Hermes path)
| Step | Owner | State |
|---|---|---|
| **GAP-1 — Hermes speaks `/mcp`** (port the proven `palace_mcp_shim` contract into `pi-neop-runtime` memory broker) | 🔨→box | **code DONE** (`pi-neop-runtime#1`, 26/26 offline). Live proof `gap1_live_proof.ts`: seat recalls its OWN write, **top-ranked + clear margin over #2**, non-empty (NO absolute cosine). Box-observed this turn: 0.358 #1, 1.85×. |
| **GAP-2 — Hermes is jailed** (hardened non-root image fed to the runtime-agnostic `isolation.py` egress jail) | 🔨→box | **code DONE** (`pi-neop-runtime#2` image; `NEURAL-ops#60` de-stubbed proof). Proven adversarially GREEN on box (egress blocked, escape refused, uid 1000, RO rootfs). Re-run through the de-stubbed harness pending. |
| **Floor fix — recall doesn't ride the edge** (hybrid lexical+vector + adaptive floor) | 🔨→deploy | **code DONE** (`Mempalace#29`, tsc clean). Live proof = `convex deploy` (builds `search_content` index + backfills) + before/after recall check. |
| Governance flip (Policy v1) | ⛔+🔨 ~1d | set `approval-policy-v1.md` + env toggles; seam live-proven |
| **T9 — first real NEop** | ⛔ you | explicit STOP-and-ask |

**The one box-session that unlocks M1b:** restart the stopped T0/T7 box (`i-041f52751ddc449a8`) → deploy
`Mempalace#29` → re-run `gap1_live_proof.ts` (rank+margin bar) + `gap2_jail_proof.py` (de-stubbed harness) →
**both green = M1b unlocked.** Red on either = a finding at file:line, with the bars set so a near-miss can't pass.

### Track B — A human chats their twin (M2) · ~1–2 wk after M1b
`nc-channels` Matrix adapter (built offline+green per memory; ship it) → reuse `matrix.neuraledge.in` → talk
via a **stock Element client** (lean first-contact). **`nc-web` is built in parallel** (UI plan) but is
**off** the first-contact path — it must not gate first contact.

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
| **zero isolation violations 30d** | ✅ mechanism proven (4-layer ACL + audit; GAP-2 jail proven on Hermes) · needs the ⛔ 30-day window |
| 6 meta-NEops · dashboard · pen-test | ✅ 4 wrapped · 🔨 dashboard + 2 meta-seams · ⛔ pen-test |

## The date math (why earliest Day-90 ≈ late Oct 2026)
The only lever on Day-90 is starting the 90-day fidelity clock sooner = onboarding ≥5 seats sooner = M2 done
= M1b done = **the box-session that proves GAP-1 ∧ GAP-2**. Back-calc to hit Day-90 = **D**:
- M1b box-session by ~D−104 · Matrix adapter by ~D−100 · M2 + onboarding by **D−90**.
- Anchored to the box-session ~now *and a pass*: M1b → M2 (~2 wk) → onboard → **earliest Day-90 ≈ late Oct
  2026** (Day-180/≥0.75 ≈ late Jan 2027).
- **Every ⛔ slip moves Day-90 one-for-one** — the fidelity calendar can't absorb slack.

## The one variable that matters
Not agent build — it's **your go-cadence on the gated steps, chiefly the one M1b box-session** (deploy
`Mempalace#29` + re-run the two proofs), then onboarding. **The single highest-leverage action this week is
clearing that box-session.** Nothing else on the board moves the date. The box is the **stopped, purpose-
provisioned EC2 `i-041f52751ddc449a8`** (m7i.2xlarge, has Docker) — *restart* it; it is NOT the production
runtime (the runtime is **Fargate** — that earlier framing was a corrected false premise). "Looks like a
switch" has been a gated spike repeatedly (the embedder; the frozen-`core.py` wall; the `/mcp` floor that the
box-session just surfaced as marginal) — treat the re-proof as a spike, not a flip.

## "Will the agents run fine?" — the honest answer
The execution machinery is built + green and the substrate is live, but **no NEop has executed live on the
canonical (Hermes) runtime yet.** The remaining engineering is the two Hermes live proofs (GAP-1 memory
round-trip + GAP-2 jail) and the floor deploy — all coded, none yet run on the box together. Pass them and a
NEop executes live on Hermes — **gated** (proposing, not committing) until fidelity ramps. That is "running
fine" in the only sense the architecture allows on day one. (jcode's own box-exec was proven at T7, but jcode
is no longer the NEop runtime — that proof transfers to the QuickBuild build-assist role, not to M1b.)
