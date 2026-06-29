# NEOS Ecosystem — Execution Plan (the "how/who/when" under the L0–L5 roadmap)

**Dated 2026-06-29.** The strategic roadmap (L0–L5) answers *what makes the ecosystem ready*. This is the
**execution layer**: for every remaining piece, its **verified state**, the **next concrete action**, and
**what unblocks it** (agent-now / box / calendar / net-new / deferred). Grounded in a read-of-the-code +
read-of-the-live-account pass on 2026-06-29 — not assertions.

## The one finding that sharpens the whole plan
The roadmap's L1·2b "operational backlog" is **mostly built offline already** — its pure cores exist and
are tested; the real gap is **live wiring**, which is gated on the **same box** as L1·1a. So the box is an
even tighter bottleneck than the roadmap states: it clears 1a **and** the live-wiring of most of 2b.

| L1·2b item (roadmap state) | **Verified state (2026-06-29)** | True remaining work | Gate |
|---|---|---|---|
| nc-channels live + first contact ("AS-spike pending") | code built; **AS-contract spike already ran this session** (registration/Bearer/`m.replace` confirmed) | Synapse flip + public TLS ingress + AS task def | box/infra |
| Twin Curator maturity machine ("seam incomplete") | **`runtime/curator.py` BUILT+tested** — fidelity clock (agreement_rate_30d) + `next_maturity` + version-bump `curate()` | feed it **live** Decision-Shadow signals | box |
| Hierarchy Resolver ("not built") | **`acp/hierarchy.py` BUILT+tested** | wire into live routing | box |
| P4 fidelity-clock live wiring ("offline-proven") | consistent — `curator.fidelity` is the offline-proven piece | Decision Shadow writes a live score | box |
| P5 fleet re-wrap ≥3 NEops/seat ("partial") | planner→executor→verifier contract partial | finish + run on a live seat | box |
| embedder ranked re-proof ("one-time 6/28") | **harness now an honest repeatable Titan check** (PR #55) | run `embedder_proof.py` in-VPC on demand | box/CodeBuild |
| nc-web (real client + dashboard) | **genuinely not built**; off first-contact path | net-new UI | net-new (agent) |
| nc-audit + deletion 4-store | **genuinely not built** (the jcode `audit_tap` is separate) | propagation logic (offline) + live stores | net-new + box |
| nc-admin · secrets→keychain | **`runtime/secrets.py` BUILT+tested**; UI not built | tenant-lifecycle UI | net-new (agent) |

⇒ Of nine 2b rows, ~6 have **built+tested offline cores waiting on the box**, and only **3 are genuinely
net-new** (nc-web, nc-audit 4-store, nc-admin UI). The "operational backlog" is far smaller than it reads.

---

## The execution plan, by gate

### NOW — clearing the box (L1·1a) · **in progress this session**
The single unblock for the entire stack. **Two of three preflight gates already closed** on the live box.
| Step | State | Done-bar | Owner |
|---|---|---|---|
| Provision the box | **DONE** — `i-041f52751ddc449a8` (m7i.2xlarge, spine VPC public subnet, SSM) | instance running | agent ✓ |
| Docker daemon | **DONE** (`DOCKER_OK`) | `docker info` ok | agent ✓ |
| Model key reachable | **DONE** — Secrets Manager `neos-dogfood/OPENROUTER_API_KEY` | preflight finds it | agent ✓ |
| jcode binary | **building now** (Rust, ~1.7 GB target) | `jcode --version` | agent (in progress) |
| `preflight: READY` | pending the build | exit 0 on the box | agent |
| **T0 spike** | pending | `jcode run "remember/search"` round-trips to palace + model path green | agent → **STOP-and-show** |

### AFTER T0 (agent, on the box) — live validation + live-wiring the built cores
| Step | What it unblocks |
|---|---|
| **Live T7** — run the jail, confirm it actually blocks egress + honors lockdown | the security gate before any real data |
| **M1b** — a NEop does real, gated work (propose-not-commit) | first real-product behavior |
| **Live-wire the built 2b cores** — curator↔Decision-Shadow, hierarchy↔routing, P4 fidelity score, P5 fleet | most of 2b, now that the live seam exists |
| **nc-channels live** — Synapse flip (`enable_comms_tier`) + TLS ingress + AS task → first contact via Element | the product becomes demonstrable |

### NET-NEW, offline-buildable in parallel (agent, on your prioritization — NOT fanned out unprompted)
nc-web (UI), nc-audit 4-store deletion logic, nc-admin tenant-lifecycle UI. Conventional builds; none on the
first-contact critical path. Pick when you want them; I won't auto-spawn ten PRs that don't clear the gate.

### CALENDAR — the evidence (L1·1c) · non-compressible
Onboard ≥5 NeuralEDGE seats → fidelity ramp 0.40 → ≥0.65 → 30-day zero-isolation window → pen-test →
Day-90 declaration. **Not code.** Needs real use over real time. The curator/fidelity machinery to *measure*
it is built; what's missing is the usage.

### DEFERRED by the sequencing rule (do NOT start before L1 validates)
- **L2 (productization)** — net-new. Foundations that already exist (don't re-derive): `runtime/secrets.py`
  (env→keyring→refuse), the Terraform runtime substrate (`infra/terraform/`), per-user twin-keying
  (live-proven). Net-new: one-click provisioning, billing/metering, SSO, PrivatNEOS, E2EE, the 2nd tenant.
- **L3 (NeP economy / Marketplace)** — mostly greenfield. Foundation that exists: `runtime/flywheel.py`
  (the NeP self-improvement loop core, tested). Net-new: attestation/`nc-eval`, registry, the commerce
  layer (licensing, rental, 60/40 rev-share accounting), quality gates.
- **L5 (Physical Intelligence)** — horizon (Beta Nov'26 / GA Jan'27).

### PARALLEL — L4 GTM (not platform-gating; user-led)
Client engagements (Zoo Media, Von Albert, …) fund the stack and harden L2/L3 as a forcing function.
*(Client facts are user-provided; not independently verified here.)*

---

## Readiness verdict
- **L0:** done — on main, running.
- **L1:** ~built. Offline cores for 1a-tooling **and most of 2b** are done+tested. Gated on the **box**
  (clearing now) + the **calendar** (1c, can't be sprinted).
- **L2:** net-new; a few real foundations exist; correctly deferred until L1 validates.
- **L3:** mostly greenfield; the NeP loop core exists; the genuine long-horizon frontier.
- **L5:** horizon.

**The convergence stands, tighter than stated:** every layer above L0 is gated transitively on L1 → on the
box. The box is being cleared this session. After it: live validation + a short live-wiring pass turns most
of the "backlog" green, then the calendar runs. L2/L3 are large, real, and **deliberately not yet started** —
building them now would be building on an unproven foundation, which the sequencing rule (correctly) forbids.
