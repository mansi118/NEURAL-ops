# NEOS — End-to-End Launch Checklist (single source of truth, reconciled 2026-07-05)

> **Confidentiality:** INTERNAL — NeuralEDGE / Synlex.
> **What this is.** The one executable checklist to a live Matrix/Element launch, reconciled against the
> repo and the **DECIDED** runtime ADR. It **supersedes the Phase-0 framing of the chat "End-to-End Launch
> Plan"**, which was authored without `ADR-neop-runtime.md` in context and reverted to a pre-ADR premise
> (the exact document-vs-document drift that ADR exists to kill).
> **Owner tags:** `[A]` agent-buildable offline · `[U]` yours (keys / applies / sign-offs) · `[BOX]` proven
> live in a box session, never offline against a mock.
> **Provenance tags** (the honesty rule that made this correction necessary applies to the correction too):
> `✅⟨S⟩` verified at file:line **this session** · `📄⟨ADR⟩` inherited from `ADR-neop-runtime` (2026-06-30,
> weeks old) about a repo **not opened this session** → **re-confirm at file:line before acting on it.**

---

## § SESSION DELTA — 2026-07-07 (folded into the 07-05 SSOT; phase bodies below still hold)
Verified this session against the live repos. **None of this re-opens Phase 0** — it advances Phase 1's model
path and corrects two now-stale status lines. `✅⟨S07⟩` = verified at file:line 2026-07-07.

1. **The chat "End-to-End Launch Plan" resurfaced and was re-declined.** Its Phase-0 "adjudicate the runtime"
   reverts to the pre-ADR premise this doc supersedes (§SETTLED Premise 3). Runtime stays **DECIDED = Hermes**.
2. **Deploy-topology DECIDED: Bedrock-Nova-in-VPC** (sealed spine, no NAT; Fork 1 = provisioning). PR **#94**
   merged. `deploy-topology-design.md`. The single model-egress finding surfaced at three layers (runtime never
   reached a model · wrapper had no model path · historical write-quarantine) — one root cause, one fix.
3. **The model path is now a specified offline build, registry-verified** (`modelbroker-bedrock-provider-design.md`;
   PR **#95**): `pi-neop-runtime/src/brokers/model.ts` gets provider **`"amazon-bedrock"`** (pi-ai `KnownProvider`),
   bearer **`AWS_BEARER_TOKEN_BEDROCK`**, region **`ap-south-1`**, model **`apac.amazon.nova-lite-v1:0`** (Converse/
   Nova). **NOT yet implemented** — `PROVIDER_KEY_ENV` still holds only anthropic/openrouter (`model.ts:37-40`).
   `✅⟨S07⟩` This is the **~10-line change** that is the last offline model-side piece. One `[BOX]` question left:
   does pi-ai's `region` map bare→`apac.*`, or must the profile id be passed directly.
4. **Reconciles Phase-1's "set the model key":** it is no longer Anthropic-direct-only. Two live options, both real
   — **Anthropic-direct** OR **Bedrock-Nova-in-VPC (ap-south-1 bearer)**, the sealed-spine path the wrapper build
   targets. `ADR-llm` holds: **provider is orthogonal to runtime** (§SETTLED Premise 4). *(us-east-1 token 403s
   against the spine — mint ap-south-1; rotate the transient verification token.)*
5. **`pi-neop-runtime` IS checked out on this box** (`/mnt/c/Users/LENOVO/Desktop/pi-neop-runtime`) — corrects
   Phase-1's "not checked out" note. GAP-1 target `src/brokers/memory.ts` is the live-retrieval seam (re-confirm).
6. **Phase-2 correction — the transport is coded, not a bare stub.** `nc_channels/service.py`: `serve()` (`:132`),
   `_cs_api_call` real CS-API send (`:196`), fail-closed `_seat_forward` (`:214`, the Wire-B seam). `✅⟨S07⟩`
   Still **`[BOX]`-gated against real Synapse** (LIVE-SEAM LAW) — but no longer `NotImplementedError`. **8 seam PRs
   merged** this arc; **Wire-B DECIDED**: nc-channels forwards `raw` to the Hermes seat over HTTP
   (`ADR-wire-b-forwarding.md`), not bridge-ported-into-Hermes.

⇒ **Next offline action:** implement the Bedrock provider (delta 3) + unit-test. Then Phase 1 is `[BOX]`/`[U]`.

---

## § SETTLED PREMISES — read before planning anything (put here so the next session inherits the decision *with* its proof)
A decision recorded only in an ADR lost to a plan that never cited it. So it is restated here, with evidence,
where the next session will actually be looking:

1. **The NEop runtime is Hermes** — `mansi118/pi-neop-runtime` (Node/TS, on `@earendil-works/pi-agent-core`).
   **This is DECIDED, not open.** `ADR-neop-runtime.md:3` — *Status DECIDED 2026-06-30* (owner ML). `✅⟨S⟩`
2. **The Python runtime is NOT the vehicle** — and this is on evidence, not preference. `runtime/core.py:4-6`
   self-declares *"reference / test-mode … Production Hermes (Node) implements the same contract"*; its
   `ModelBroker` **raises on live tools**. It is an orchestrator + phase-state-machine, **not** a
   prompt→LLM→tool→observe loop (ADR child-1). `✅⟨S⟩` (read `core.py:1-20` this session).
3. **Do not re-adjudicate the runtime toward `core.py`.** The chat plan's Phase 0 did exactly that; the trace
   already answered **NO** at file:line. Re-opening it is re-litigating a settled, evidence-grounded decision.
4. **The LLM provider is orthogonal** to the runtime (`ADR-llm.md`) — either runtime can use either provider.

**Two epistemic weights — do not confuse them (this is the seam a future session could pry):**
- `✅⟨S⟩` **settled premises are CLOSED to adjudication.** Cite them, build on them, do **not** reopen. The
  question "is Hermes the runtime" is decided; re-asking it is the exact drift this block exists to stop.
- `📄⟨ADR⟩→re-confirm` tags are **OPEN to verification, NOT to adjudication.** They were true weeks ago about
  a repo not opened this session. You may **not** trust them without re-tracing, and you may **not** stretch
  "re-confirm" into "re-decide." Step zero of any work touching one is re-tracing the live repo at file:line.
- **Decision vs evidence — hold both:** the *decision* (Premise 1: Hermes) is settled; the *evidence's
  current state* is verify-on-contact. Re-tracing `pi-neop-runtime` for GAP-1 re-verifies the evidence the
  ADR rests on — that is expected and correct. **The ONLY thing that can reopen Premise 1 is a fresh trace
  showing the cited file:line evidence no longer holds.** If a re-trace finds drift (e.g. `memory.ts` moved,
  or `core.py:4-6` no longer self-declares reference-mode), that is **"the ADR's evidence is stale — flag
  it"**, and **the decision still stands until a NEW trace with NEW evidence overturns it** on the record —
  never a silent re-open on a `→re-confirm` tag.

⇒ **Phase 0 is DONE.** The real pre-M1b work is GAP-1 ∧ GAP-2 on Hermes (Phase 1).

## § THE LIVE-SEAM LAW — July-1, promoted from incident to law (applied at *every* seam below)
The dead-embedder incident, the Matrix-mock trap, and #30's fusion failure are **three instances of one
class**: our code first meeting real infra. One law governs all of them:
1. **Offline green proves the *logic*, never the *seam*.**
2. **Only a live run against real infra proves the seam.** match-to-mock ≠ match-to-Synapse; match-to-shim ≠
   match-to-live-Convex. A ported/wrapped component is new surface until it round-trips against the real thing.
3. **Graceful-empty is FAILURE**, held literally — an empty/absent result is a *failed proof*, not a soft pass.
   (This is the inverse of the spine smoke's empty-tolerance, which is exactly why it missed a dead embedder.)
4. **Reproduce the *real* behaviour before claiming success** — a real ranked hit; a real reply in the room.
**Seams this law governs:** GAP-1 (Hermes → live Convex memory) · the Matrix live-wire (`serve()`/
`_cs_api_call` → real Synapse) · #30 fusion verification (fresh-write recall → live index). Same law, thrice.

---

## Phase 0 — Runtime adjudged ✅ DONE (do not re-open)
- [x] `[A]` Runtime traced at file:line, three children (`ADR-neop-runtime.md:66-81`). `✅⟨S⟩` (ADR read)
- [x] `[U]` ML named Hermes (`pi-neop-runtime`) + chose the M1b path (port + parallel jail-prep, no bridge).
- [x] `[A]` ADR flipped PROPOSED → **DECIDED**; `superseded-by` banner on the jcode-adapter plan.
- **Gate:** ✅ cleared.

## Phase 1 — Hermes earns M1b (the real pre-launch engineering; the chat plan under-scoped this)
Both gaps live in **`pi-neop-runtime` — an external repo NOT checked out on this box.** Nothing in Phase 1 is
advanceable from this WSL box; it needs the repo + a box for the live proofs. **Every file:line below tagged
`📄⟨ADR⟩` is from the weeks-old ADR and MUST be re-confirmed against the freshly-checked-out repo first —
`memory.ts` may have moved or half-closed since 2026-06-30.**

- [x] `[U]` **Check out `pi-neop-runtime`** — now present on this box (`/mnt/c/Users/LENOVO/Desktop/pi-neop-runtime`,
      §DELTA-5); still needs a real *box* (Docker + spine) for the live proofs.
- [ ] `[A]` **Re-trace, step zero of the real work** — re-confirm the two blockers at file:line in the live
      repo *before* touching them: (a) `src/brokers/memory.ts` still throws on live PALACE retrieval; (b) no
      container/egress-jail artifact present. Verify the child, not "the ADR said so." `📄⟨ADR⟩→re-confirm`
- [ ] `[U]`/`[A]` **Wire the model path** (updated by §DELTA-3/4 — no longer Anthropic-direct-only). `[A]`:
      implement the **`amazon-bedrock`** provider in `resolveLiveModel()` (`src/brokers/model.ts:37-40,147-163`;
      `✅⟨S07⟩` bedrock not yet present) — the ~10-line registry-verified change. `[U]`: set the key — either
      **Anthropic-direct** (`ANTHROPIC_API_KEY`) OR **Bedrock-Nova-in-VPC** (`AWS_BEARER_TOKEN_BEDROCK`,
      **ap-south-1**), the sealed-spine path. Provider is orthogonal to runtime (§SETTLED Premise 4).
      (OpenRouter is the parked-rotation key — don't route brains through a secret you've deferred rotating.)
- [ ] `[A]` **GAP-1 — port the `/mcp` contract.**
      **Source (verified this session):** `neop_jcode_adapter/palace_mcp_shim.py:20-24` — body
      `{tool,palaceId,neopId,params}` + header `X-Palace-Neop`, scope **baked from env**, **fail-closed on
      blank PALACE_ID/NEOP_ID** (blank → palace defaults `_admin`, which **bypasses all ACL**). `✅⟨S⟩`
      **Destination (re-confirm):** `pi-neop-runtime/src/brokers/memory.ts:23` — today `throw "live PALACE
      retrieval not wired"`, `write()` a no-op sink. `📄⟨ADR⟩→re-confirm`. Port scope-bake + ACL-respecting
      client + forward-looking Ed25519 sign. **The throw is honest (it refuses to fake) — replacing it is
      exactly a live-seam event: match-to-shim is not match-to-live-Convex.**
- [ ] `[BOX]` **GAP-1 proof — live ranked-memory run on Hermes** (LIVE-SEAM LAW). First time Hermes-native
      retrieval hits real Convex; it can fail the identical way #30's fusion did — green offline, empty/wrong
      against the live index. **empty = FAIL, held literally** (`embedder-as-built.md:18`). **Trigger to
      green:** a reproduced real ranked hit on real memory — not "memory.ts returned something."
- [ ] `[A]` **GAP-2 — containerize Hermes under the T7 egress-jail spec.**
      **Blast-radius note (state it, don't discover it):** the swap from the Python runtime to Node moves the
      jail target — the T7 spec as previously specced may carry **Python-shaped assumptions**. GAP-2 therefore
      = **validate the jail spec against the Node process model**, then build the artifact (rootfs RO, caps
      dropped, egress confined to the palace, metadata + internet blocked). Not "apply T7 unchanged."
- [ ] `[BOX]` **GAP-2 proof — Hermes-native isolation, equivalent to live T7.** The jcode jail result does
      **not** transfer. **Trigger to green:** clean red-team isolation on the Node runtime.
- [ ] `[A]` **Build M1b** — first real NEop full-loop (receive → plan → retrieve real ranked memory → act →
      verify) on Hermes, against the real stack.
- [ ] `[U]` **T9 go** — box-session authorization for the first real NEop run (CLAUDE.md STOP-gate).
- **Gate:** M1b starts **only when GAP-1 ∧ GAP-2 are both green** (`ADR-neop-runtime.md:108-120`).
- **Exit:** "it thinks and remembers," proven end-to-end on Hermes.

## Phase 2 — The Matrix front door (launch surface)
Mechanics **pre-flighted in PR #71**; the live build/apply is the box window. Ordering per
`nc-channels-transport-deploy-design.md` §"The live window".
> **▶ Bar 1a box session → `docs/deployment/bar1a-box-runbook.md`** (cold, copy-paste, your-hands-only).
> It SUPERSEDES the Fargate/EFS + `matrix.neuraledge.in` framing in the `[BOX]` lines below: real HS is the
> EC2 Synapse, `server_name = neuraledge.in` (#77/#85), regex `@neop_.*:neuraledge\.in`, bridge co-located
> on the matrix box (no ALB, no palace). Wire model + B-fwd decision: `wiring-map.md` + `ADR-wire-b-forwarding.md`.
- [x] `[A]` **G-A server_name** = `matrix.neuraledge.in` (immutable-safe, self-contained, no apex
      `.well-known`), baked in `phase2/phase3.tfvars`. `✅⟨S⟩`
- [x] `[A]` **Held nc-channels ECS TF** (`nc-channels.tf`, `enable_nc_channels=false`) + live-window ordering
      + SSM/Element-Desktop reachability — PR #71. `✅⟨S⟩`
- [ ] `[U]` **Flip comms tier** — `enable_comms_tier=true` + `terraform apply -var-file=phase2.tfvars`.
- [ ] `[BOX]` **VERIFY server_name baked** = `matrix.neuraledge.in` on the live HS (the one irreversible byte).
- [ ] `[BOX]` **G-C, HS side** — mint `as_token`/`hs_token` → registration YAML on EFS → `homeserver.yaml
      app_service_config_files` → restart Synapse (transport-deploy-design 3c).
- [ ] `[BOX]` **Prove the transport** (LIVE-SEAM LAW) — `serve()`/`_cs_api_call`/`_seat_forward` are now
      **coded** (`nc_channels/service.py:132/196/214`, `✅⟨S07⟩` — see §DELTA-6), no longer a stub; hand-drive
      `_cs_api_call` against **real Synapse** and exercise `serve()` end-to-end. **Coded ≠ proven — the seam is
      still `[BOX]`, never faked offline.** Reproduce a real `@neop_*` reply in the room before claiming it.
- [ ] `[U]` **G-C, AS side** — flip `enable_nc_channels=true` + apply (comes up serving, not crash-looping).
- [ ] `[U]` **Reachability** — SSM port-forward + **Element Desktop** over `http://localhost:8008` (alpha, no
      TLS/`.well-known`), **or** bring G-B (public ALB + ACM) forward for outside-team access.
- **Exit:** a person reaches NEOS on Matrix through Element.

## Phase 3 — Governance + onboard = **LAUNCH**
- [ ] `[U]` **Flip governance** for the dogfood tenant — Approval Policy v1 (`acp/approval.py` wired;
      `docs/decisions/approval-policy-v1.md` drafted `✅⟨S⟩`) + env toggle. A toggle, not a build.
- [ ] `[U]` **Onboard founding seats** — each runs the ≤15-min Interviewer → twin v0 (`agents/interviewer`).
      Real people; the fidelity clock + the 30-day observation window **start here**.
- **This is the launch.** It does not wait on Phase 4.

## Phase 4 — Earn-out (runs ON the live system, in parallel — compressed, not faked)
- [ ] `[BOX]` **Cross-tenant isolation red-team** — 2nd throwaway tenant palace, cross-REAL-tenant attempt.
      **Real gate before any 2nd real tenant** (today isolation is by-construction + single-tenant T7, NOT
      adversarial cross-tenant — `ADR-neop-runtime.md:125-128`). Days, not 90.
- [ ] `[U]` **Book the pen-test** now; runs on the live in-VPC system in the first weeks.
- [ ] live **Fidelity ≥ 0.65** — usage-gated; heavy dogfooding accelerates it.
- [ ] calendar **30-day zero-violation window** — the one un-compressible item; **runs from the Phase-3
      launch, concurrently** ("launched, clock already running").
- [ ] `[A]` **6 meta-NEops + dashboard** — parallel track (see below).
- [ ] `[U]` **Rotate PAT + OpenRouter** — un-park it; ~2 min.
- **Go-wider bar:** internal launch stands on Phase 3; a **2nd real tenant** needs isolation-red-team green +
  pen-test passed + *enough* clean operation. Evidence bar, shorter than 90, **not zero.**

## § Parallel track — does NOT wait on M1b's box dependency
The meta-NEops are offline-provable and Day-90 needs all six live. Keep them moving so the box session isn't
the critical path for the whole program:
- [ ] `[A]` **Twin Curator** maturity machine — offline-provable now.
- [ ] `[A]` **Hierarchy Resolver** — offline-provable now (`agents/hierarchy-resolver`).
- [ ] `[A]` **#30 fusion verification** — live-memory seam; governed by the LIVE-SEAM LAW above (empty=FAIL).
- [ ] `[A]` remaining meta-NEops toward the six-live Day-90 bar.

---

## Critical path (corrected)
**Phase 0 DONE (ADR=Hermes) → re-trace + GAP-1 ∧ GAP-2 green on `pi-neop-runtime` → M1b/T9 → comms flip +
Element transport (PR #71) → governance + onboard = LAUNCH →** earn-out on top, in parallel.

## What is NOT done — stated plainly (no hollow-green)
- **Phase 1 is not advanceable from this box** — `pi-neop-runtime` is not checked out here; GAP-1/GAP-2 live
  proofs are box-gated. GAP-1/GAP-2's file:line specifics are **on-ADR-record, pending re-confirmation.**
- `serve()`/`_cs_api_call`: **still raising by design**; built live at the box, never offline.
- No `terraform apply`, no comms tier, no governance flip, no onboarded seat: all `[U]`/`[BOX]`.
- The 30-day window + the cross-tenant red-team are **real gates**, compressed + parallel, not skipped.

## Two things fully in your power without the box
1. **This reconciliation** — done (this doc).
2. **The offline pre-flight** — done (PR #71): immutable `server_name` baked before any apply, ECS TF
   written-but-held until `_cs_api_call` is hand-proven, reachability path confirmed.
Everything else on the launch path is `[U]` (a key, an apply, a sign-off) or `[BOX]` (a live proof). The
integration/deploy itself cannot be finalised from this WSL box — and after the Phase-0 catch, that's the
*correct* outcome: the plan now points at the true critical path instead of executing a false one.
