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

## Milestone 1 — Backend NEops executing on live AWS  ·  **T0 + ~3–5 days** (mostly `[A]`)
The smallest remaining engineering. Bottleneck = your go-cadence, not unbuilt code.
| Step | Owner | Notes |
|---|---|---|
| Merge #41 + #25 | `[U]` 2 min | embedder lands on both mains |
| Rotate GitHub PAT + OpenRouter key | `[U]` 2 min | parked-not-closed; real downside w/ live billing |
| **Model key for NEop dispatch** | `[A]` ~1–2 d | OpenRouter key is **on hand** in `.env` — route the model broker to it, set it in the Convex/runtime env (same play as the embedder), prove ONE live dispatch. ⚠ which env var the runtime reads (CONFIRM) |
| Governance flip (Policy v1) | `[A]`+`[U]` ~1 d | set `approval-policy-v1` + env toggles; seam already proven |
| **M1 = a NEop runs end-to-end on AWS, gated** | | retrieval works underneath it |

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

## Worked example (illustrative anchor: T0 = 2026-06-30)
| Milestone | Date | Driver |
|---|---|---|
| M1 — backend NEops executing | **~2026-07-04** | merge + model key + governance |
| M2 — human chats their twin (lean) | **~2026-07-18** | the Matrix adapter build |
| Onboard ≥5 (fidelity Day 0) | **~2026-07-21** | your go |
| **Day-90 (earliest declaration)** | **~2026-10-19** | Day 0 + 90 |
| Day-180 (≥0.75 target) | ~2027-01-17 | usage ramp |

## Back-calc rule (deadlines against the gates)
To hit a chosen **Day-90 = D**: onboard by **D − 90**; M2 done by **D − 90**; M1 by **~D − 104**; so the
**model-key + governance build must start by ~D − 107**, and the **Matrix-adapter build by ~D − 100**.
Earliest D ≈ **mid-to-late October 2026** if onboarding starts late July. Slipping any `[U]` gate slips D
one-for-one — the calendar pole (fidelity) cannot absorb it.

## The one variable that matters
The engineering left to *first-live* is small and mostly bounded. The dominant variable is **your
go-cadence on the gated steps** (merge, rotate, model-key go, onboarding) and whichever traps the
**untraced surfaces** (`nc-channels`, `nc-web`) still hide — the embedder just proved tracing can surface
bigger-than-they-looked steps. Once #41 lands, everything downstream is execution and time.
