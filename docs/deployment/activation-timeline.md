# Activation Timeline — three "live"s, dated

The word "live" hides three milestones of wildly different size. Collapsing them is where false optimism
hides, so they're split. Dates are **relative to T0** (your go-gates) with an **illustrative anchor**;
move T0 and everything shifts. The long pole (fidelity) is **calendar, not code** — it cannot be sprinted.

> **Current state (2026-06-28) — further than the three-bucket framing assumed.** The AWS apply is
> *already crossed*: the dogfood spine is LIVE (deployed-stack smoke 7/7) and the **embedder is proven**
> (Bedrock Titan via PrivateLink, ranked retrieval). So M1 is not "days bottlenecked on the apply" — the
> apply is done; what remains is merge + model-key + governance. We're at the front of M1, not before it.

Legend: `[A]` agent-buildable · `[U]` your gate (decision/credential/calendar) · ⚠ untraced (may hide a step).

---

## Milestone 0 — Spine + embedder live on AWS ✅ DONE (2026-06-28)
Spine applied (VPC + Convex SoT + runtime + bridge), smoke **7/7**, embedder **live + proven**. PRs #41
(NEURAL-ops) + #25 (Mempalace) open to merge. Billing (~$100/mo) active.

## Milestone 1 — split, because tracing the model killed the "days of `[A]`" framing
The substrate is done; **a NEop actually executing** is a gated milestone, not config. Two sub-parts:

### M1a — backend SPINE live + proven ✅ DONE
Merge #41 + #25 (`[U]` 2 min) · rotate creds (`[U]` 2 min, parked-not-closed). Memory/ACL/audit/**embedder**
all live + proven on AWS. This is what "the backend is live" actually means today.

### M1b — a NEop runs plan→execute→verify with a real model  ·  **GATED (not `[A]` config)**
The load-bearing child — the model — has no quick wiring, traced 2026-06-28:
- `runtime/core.py` `ModelBroker` is **unit/cassette-only by design**; `dispatch` builds it internally,
  **no injection seam**. core.py is the **frozen deterministic reference** — a live model path there is the
  forbidden 2nd change (byte-identical except the one sanctioned AwaitingApproval edit). The OpenRouter key
  being on hand is necessary-not-sufficient: there is **no sanctioned place in the dispatch loop to call it**.
- The **intended** live runtime is the **jcode adapter** (`neop_jcode_adapter/`, branch
  `feat/neop-jcode-adapter`, **not merged** — only the T1 shim built). Its plan makes **T0 a go/no-go
  STOP-and-show gate**; CLAUDE.md: **"STOP and ask before T9 (first real NEop) and before client data."**

| Step | Owner | Notes |
|---|---|---|
| **jcode T0 spike** (one jailed jcode proc → shim → live palace round-trip) | `[U]` go/no-go | newly feasible: palace ✅ **live on AWS**, Docker ✅ via CodeBuild/ECS. Needs a runnable jcode binary + the Docker jail + a model key (OpenRouter on hand — jcode-configurable; Anthropic not on hand). **STOP-and-show after T0.** |
| jcode adapter T1–T6 (shim/config_render/audit/jail/promoter) | `[A]` | T1 built (branch); the rest in order, **stop at T7** (the gate you run) |
| Governance flip (Policy v1) | `[A]`+`[U]` ~1 d | gates dispatch once it's live; seam proven |
| **M1b = a NEop runs end-to-end on AWS, gated** | `[U]` T9 | first real NEop = explicit STOP-and-ask |

> **Correction (honest):** the earlier "model key → dispatch, `[A]`, ~days" line was false-optimism. The
> live model path is the jcode adapter behind a go/no-go gate — bigger than it looked, exactly the trap the
> embedder foreshadowed. The agent will NOT build a live model into core.py (frozen) and will NOT run T0/T9
> unilaterally (the discipline's STOP gates).

## Milestone 2 — A human opens a chat and talks to their twin  ·  **M1 + ~1–2 weeks** (the real build)
This is the milestone most people mean by "agents live." `nc-channels` / `nc-web` / `nc-audit` are
**not built yet** (pre-S0 gap, not just un-deployed). **Take the lean path to first-contact:**
| Step | Owner | Notes |
|---|---|---|
| `nc-channels` Matrix adapter (Matrix ↔ orchestrator bridge) | `[A]` ~1–2 wk | ⚠ untraced — like the embedder, tracing may surface bigger-than-they-look steps |
| Channel infra apply (use existing `matrix.neuraledge.in`; Synapse public ingress if needed) | `[U]` | homeserver already exists → skip standing one up |
| Talk to your twin from a **stock Element client** | | skips the custom React app |
| `nc-web` (Slack-shape client) | `[A]` after | **off the first-contact path** — build post-M2 |

## Milestone 3 — Twins worth trusting  ·  **calendar, ~90 days from onboarding** (not compressible)
The agents are "live" at M2; the *product* (a twin you'd let act on `delegate`) is a usage ramp by design.
| Step | Owner | Notes |
|---|---|---|
| Onboard ≥5 seats = **Day 0** of the fidelity clock | `[U]` | Interviewer seeds each `twin.md` v0 |
| Decision Shadow runs; fidelity ~0.40 → **≥0.65 @ Day 90** | calendar | per-user twin (keying already done) — measures the person |
| 30-day zero-isolation-violation window | calendar | mechanism live-proven (4-layer ACL + audit) |
| Pen-test · harden · **Day-90 declaration** | `[U]` | "production-ready" — never agent-declarable |

---

## Worked example (anchor: T0 = the jcode go/no-go decision — **your gate, not a date the agent sets**)
The pivot is no longer "merge + model key" (that was the false-optimism); it's **the jcode T0 decision**.
Dates below assume T0 greenlit ~2026-06-30 AND T0 passes — illustrative only.
| Milestone | Date (if T0 greenlit ~Jun 30 & passes) | Driver |
|---|---|---|
| M1a — spine live | ✅ now | done |
| M1b — a NEop executes (jcode T0→T6→T9) | **~2026-07-11** | the jcode adapter + the T0/T7/T9 gates |
| M2 — human chats their twin (lean) | **~2026-07-25** | the Matrix adapter build |
| Onboard ≥5 (fidelity Day 0) | **~2026-07-28** | your go |
| **Day-90 (earliest declaration)** | **~2026-10-26** | Day 0 + 90 |
| Day-180 (≥0.75 target) | ~2027-01-24 | usage ramp |

## Back-calc rule (deadlines against the gates)
To hit a chosen **Day-90 = D**: onboard by **D − 90**; M2 done by **D − 90**; M1b (a NEop executes) by
**~D − 104**; so the **jcode T0 go/no-go must be greenlit by ~D − 118** (T0→T6 + the T7/T9 gates take time),
and the **Matrix-adapter build by ~D − 100**. Earliest D ≈ **late October 2026** if T0 greenlights now and
passes. Slipping any `[U]` gate slips D one-for-one — the calendar pole (fidelity) cannot absorb it.

## The one variable that matters
The engineering left to *first-live* is small and mostly bounded; the **substrate (spine + embedder) is
live and proven.** The dominant variable is **your go-cadence on the gated steps** — chiefly the **jcode T0
go/no-go** (the live-execution gate the discipline says to STOP-and-show on), then onboarding — and whichever
traps the **untraced surfaces** (`nc-channels`, `nc-web`, the jcode T1–T6 integration) still hide. The
model just proved it again: what looked like "set a key" was a frozen-core.py wall + a gated adapter. The
honest read stands — what's left to first-live is mostly **your prerequisites and the trust calendar**, not
a mountain of agent build; but the live-execution path is a **sanctioned spike, not a config flip**.
