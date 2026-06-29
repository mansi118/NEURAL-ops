# Go-Live Checklist — door open (weeks) → trust clock (calendar)

**Dated 2026-06-29.** "Live as a product" = a real person who isn't us logs in, talks to their twin,
gets useful work back. **Acceptance** of that as production-ready = the Day-90 gate (fidelity ≥0.65,
30-day clean-isolation window, pen-test) ≈ **Oct 26, 2026** — calendar-bound, never agent-declarable.
So this splits into **get the door open (≈4–6 wk, mostly your gate-cadence)** then **let the clock run
(~90 days)**. Dates are back-calculated from the Oct 26 anchor; every `[U]` slip moves Day-90 one-for-one.

Legend: `[U]` your gate · `🔨` agent-buildable · `cal` calendar (non-compressible). Anchor: T0 greenlit ~Jun 30 **and passing**.

| # | Step | Owner | Gate / done-bar | Target | Status |
|---|------|-------|-----------------|--------|--------|
| 0 | **Provide a Docker box for T0** (the EC2 m7i.2xlarge already runs the runtime) | `[U]` | agent can reach Docker + a jcode binary + the model key on that host | this week | ⛔ open — the one unblock |
| 1 | **jcode T0 spike** — one jailed proc → shim → live palace round-trip | `[U]` go/no-go | round-trip + model-key path green; **STOP-and-show** | ~Jun 30 (D−118) | run-book ready (`jcode-t0-spike-runbook.md`) |
| 2 | jcode **box-exec** — `_docker_run` · supervisor `_spawn` · egress firewall | 🔨 (on box) | the 3 stubs; everything they call is built+green | T0+days | offline parts done |
| 3 | **Governance flip** — Policy v1 (`approval-policy-v1.md`) + env toggles | `[U]`+🔨 ~1d | approval seam live (already proven on self-host) | with M1b | seam wired |
| 4 | **T9 — first real NEop** executes plan→exec→verify, gated | `[U]` | a NEop does real work on the live spine (proposing, not committing) | **~Jul 11** (M1b) | STOP-and-ask |
| 5 | **`nc-channels`** Matrix AS adapter → existing `orchestrator.handle` seam | 🔨 ~1–2 wk | Matrix event → twin → streamed reply, **via stock Element** | **~Jul 25** (M2) | traced (`nc-channels-trace.md`) — the untraced surface, now scoped |
| 6 | Deploy Synapse + public client ingress (reuse `matrix.neuraledge.in`) | `[U]` | homeserver reachable; AS registered | with M2 | `synapse.tf` built, gated off |
| 7 | `nc-web` Slack-shape client | 🔨 | the real UI; **parallel — does NOT gate first-contact** | post-M2 | off critical path |
| 8 | **Onboard ≥5 NeuralEDGE seats = Day 0 of the fidelity clock** | `[U]` | Interviewer seeds each `twin.md` v0; **you are the alpha tenant** | **~Jul 28** | the single highest-leverage date |
| 9 | Fidelity ramp 0.40 → **≥0.65**; 30-day zero-isolation window; pen-test | cal + `[U]` | Decision Shadow runs on real usage | ~Jul 28 → **Oct 26** | mechanism proven; clock not started |
| 10 | **Day-90 declaration** (alpha = NeuralEDGE itself) | `[U]` | the 4 acceptance criteria all true | **≈ Oct 26, 2026** | not agent-declarable |
| 11 | First *paying* tenant (≥0.75 ramp) | `[U]` | a later bar than Day-90 — prove it on ourselves first | **≈ Jan 24, 2027** (D-180) | don't conflate with Day-90 |

## The one line
**T0 → M1b → nc-channels → onboard your team → let it ramp.** Steps 0–8 are ~4–6 weeks and mostly your
gate-cadence; steps 9–11 are the calendar. The only lever that pulls Oct 26 earlier is **onboarding sooner**,
which routes through M1b → T0 → **the box**.

## Two things off the technical critical path but ON the product path (easily skipped)
- **You're the first customer — onboard yourselves for real, not as a test.** Five NeuralEDGE seats using
  it daily is the fastest way to surface what's broken about the *product* (not the infra), and it's literally
  what Day-90 requires. Treat your own onboarding as the launch, because it is.
- **"Live as a product" externally (paying) is later than Day-90.** Day-90 is the NeuralEDGE alpha; the first
  paying tenant is the Day-180 bar (≈ Jan 24, 2027). "We're running it" ≠ "we can sell it" — be clear-eyed
  about that with anyone you pitch.

## What's already true (so the checklist starts from reality)
Substrate LIVE on AWS (smoke 7/7); merged code rolled to prod (M2 OpenRouter + jcode adapter; bridge→runtime,
3/3 healthy, functional 7/7). Embedder Titan@1024 ranked-proven (2026-06-28). The whole offline runway is spent.
Refs: `path-to-day-90.md`, `activation-timeline.md`, `nc-channels-trace.md`, `production-readiness.md`.
