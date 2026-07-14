# Execution plan — take Track 1 + Track 3 from code-complete to LIVE (2026-07-14, session 2)

Authoritative sequencer for the current state. The Track 1 + Track 3 CODE is merged (see the PR table
below); everything here is a **deploy, a flip, a key/credential step, or a small net-new build**. Strict
dependency order — **Step 1 (palace deploy) unblocks everything**. Ownership is marked `[you]` (ML —
holds the admin key / IAM / prod-flip authority) or `[agent]` (buildable/executable without those).

Cross-references for low-level mechanics (do not duplicate here): `redeploy-after-merge.md` (image
rebuild + seat roll), `dogfood-spine-runbook.md` (spine bring-up), `go-live-checklist.md` (live gates).

## What merged this session (the code these steps activate)
| PR | Repo | What |
|----|------|------|
| #15 | pi-neop-runtime | write-trigger: per-turn `shadow_prediction` + `memory_candidate` run_events (best-effort) |
| #33 | Mempalace_NEOS | twin CAS (`baseVersion`) + `twin_versions` history + rollback |
| #34 | Mempalace_NEOS | Gate-D verify (`edgeIdentity.ts`) + `neop_keys` registry + `ENABLE_BRIDGE_IDENTITY` flag |
| #139 | NEURAL-ops | shim signs `X-NEop-Identity` (Ed25519 over `${palaceId}\n${neopId}\n${tool}`) |
| #138 | NEURAL-ops | governance factory `approval_from_env` (report_only default-off; enforce gated by ack) |
Already-merged prior: palace #31 (run_events), #32 (vault_promoted); NEURAL-ops #127/#128/#130/#133/#134/#135; pi-neop #14 (/seat/verdict).

---

## STEP 1 — Palace `convex deploy` (THE first domino)  `[you]`

The live in-VPC self-hosted palace must register this session's schema/handlers before any new code
produces or reads live data. New surface to land: `run_events`, `vault_promoted`, `twins` CAS +
`twin_versions`, `neop_keys` + the Gate-D `/mcp` path.

### 1.0 Preconditions / the open question (resolve FIRST)
- **Determine the backend type.** Is `convex.neos-dogfood.local:3211` a **standalone self-hosted** Convex
  backend, or a **proxy fronting a cloud deployment**? This picks the key:
  - Standalone → a **self-hosted admin key** generated on the backend host:
    `docker exec <convex-backend-container> ./generate_admin_key.sh` (or the backend's documented
    `generate_admin_key` entrypoint). Deploy with `CONVEX_SELF_HOSTED_URL` + `CONVEX_SELF_HOSTED_ADMIN_KEY`.
  - Proxy-to-cloud → the matching **cloud deploy key** for that deployment (NOT the `.env`
    `dev:calculating-hamster-303` key — that targets the wrong cloud dev sandbox).
  - How to tell: check the backend container/image on the palace host (self-hosted `convex-backend` image
    ⇒ standalone) and whether `:3211` terminates locally or forwards. `<CONFIRM on the palace host>`.
- **The `.env` key is WRONG for this** — it deploys to `dev:calculating-hamster-303`. Do not use it here.

### 1.1 Run the deploy from an IN-VPC runner
`.local` won't resolve from a laptop, so deploy from CodeBuild (VPC-attached; see `outputs.tf` private
subnets) or an in-VPC bastion:
```
cd Mempalace_NEOS
# standalone self-hosted:
export CONVEX_SELF_HOSTED_URL="http://convex.neos-dogfood.local:3211"
export CONVEX_SELF_HOSTED_ADMIN_KEY="<from 1.0>"
npx convex deploy -y        # pushes schema (incl. neop_keys, twin_versions) + functions
# (proxy-to-cloud variant: CONVEX_DEPLOY_KEY=<that deployment's key>; npx convex deploy -y)
```
Convex codegen runs server-side on deploy — the hand-added `_generated/api.d.ts` entries (runEvents,
neopKeys) are only for offline tsc; deploy regenerates them.

### 1.2 Verification gate (must pass before Step 2)
Against a **scratch seat** (no prod writes), over the live `/mcp`:
- `palace_put_run_event {kind:"shadow_prediction", ...}` → `{status:"ok"}`; `palace_get_run_events` reads it back.
- `palace_put_twin` then `palace_put_twin {baseVersion:<stale>}` → `{status:"stale_base"}` (CAS live).
- `palace_get_twin_versions` shows history; `palace_rollback_twin` returns `{status:"ok", restoredFrom}`.
- `palace_is_promoted`/`palace_mark_promoted` round-trip.
- Gate-D still OFF here (ENABLE_BRIDGE_IDENTITY unset) → identity path byte-identical.

### 1.3 Rollback
Convex deploy is additive (new tables/functions). If a function misbehaves, redeploy the prior commit;
the new tables are simply unread by old code. No data migration, so rollback is a redeploy.

---

## STEP 2 — Rebuild the wrapper image + reversible spine rolls  `[agent, after Step 1]`

Mechanics: `redeploy-after-merge.md`. Summary + the session-specific bits:
1. **Rebuild** the `neos-wrapper` image so seats pick up the write-trigger (#15) + verdict endpoint (#14):
   `aws codebuild start-build --project-name neos-wrapper-build --region ap-south-1` → wait → new image tag.
2. **Roll Aria + Recon** to the new task-def revision (ECS `register-task-definition` + `update-service`),
   cluster `neos-dogfood-cluster`. **Reversible**: keep the prior revision; roll back with `update-service
   --task-definition <prior-rev>`.
3. **Redeploy the bridge** (nc_channels) so the verdict forwarder + write path are current.
4. **Apply the two schedulers** (plan-first, zero-destroy — use `scripts/tf-plan-zero-destroy.sh` from
   Step-B tooling):
   ```
   terraform plan -var enable_fidelity_scheduler=true -var enable_vault_scheduler=true \
     -var fidelity_palace_id=k17f0b36y2f7h4sbr3pqp5wxg189cvg1 \
     -var fidelity_convex_url=<in-VPC convex base> -var convex_site_url=<...> \
     -var vault_seats=aria,recon
   # assert: 0 to destroy; then terraform apply the same vars
   ```
   Flags/vars verified in `variables.tf`: `enable_fidelity_scheduler`, `enable_vault_scheduler`,
   `fidelity_palace_id`, `fidelity_convex_url`, `convex_site_url`, `vault_seats`, `fidelity_schedule`,
   `vault_schedule`, `runtime_image`.

### 2.1 Verification gate ("live" for Track 3)
Drive one **real Decision-Queue verdict** (approve/reject in the neops room) and watch the chain:
`m.neop.verdict` → bridge → `POST /seat/verdict` (200) → `palace_put_run_event kind=human_verdict` →
next fidelity fold reads it (`fidelity_runner`) → a score is written. Only then is Track 3 "live".

---

## STEP 3 — The flips (all built + gated in code)  `[you]`

### 3a. Governance report-only (safe to turn on now; enforce gated)
Set on the seat/runtime env, then observe:
```
NEOS_GOVERNANCE=report_only
NEOS_GOVERNANCE_GRANTOR=ml            # explicit; never baked
# (store=integration + PALACE_ID only if using the Convex paused_runs store)
```
Nothing blocks in report_only. After a real traffic window, read `broker.readiness()` (block_rate). When
low + stable → flip enforce: add `NEOS_GOVERNANCE=enforce` **and** `NEOS_GOVERNANCE_ENFORCE_ACK=yes`
(the code refuses enforce without the ack). Rollback: set `NEOS_GOVERNANCE=off` → `approval=None`,
byte-identical to today.

### 3b. Gate D — ENABLE_BRIDGE_IDENTITY (needs a seed + a staging check first)
Order matters — do NOT flip before seeding, or every request 403s:
1. **Seed `neop_keys`** for each live seat (`scripts/seedNeopKeys.ts`, Step-B tooling): register each
   seat's Ed25519 **public** key (derived from its `PALACE_SIGNING_KEY_REF` seed) via the internal
   `registerNeopKey` mutation. Confirm `getNeopKey` returns it.
2. **Staging crypto check**: on a staging palace, POST a real shim-signed request with the flag ON and
   confirm it verifies (proves pure-JS `@noble/ed25519` runs in the live Convex backend runtime — the one
   thing not offline-verifiable).
3. **Flip** `ENABLE_BRIDGE_IDENTITY=true` on the palace backend env. Now unsigned/unregistered callers get
   `403 denied_at_layer=edge`; the `_admin` fallback is closed. Rollback: unset the env → OFF, byte-identical.

### 3c. Twin CAS broker opt-in (watch-for-the-event, NOT now)
Only when a **2nd twin writer** exists (flywheel auto-spawn goes live, or parallel twin deltas): flip the
runtime broker (`runtime/memory.put_twin`) to pass `baseVersion`. Until then the single-writer curator
holds and the blind path is correct. Pin this in the ledger when the trigger event lands.

---

## STEP 4 — Deploy the intelligence seats  `[agent, after Step 1]`

`decision-shadow`, `twin-curator`, `vault-promoter` as additional seats via the proven additive pattern
(Recon: 3 add / 0 destroy, existing seats untouched). Config artifact prepared in Step-B (`seats` map
entries + `neop_path` per agent, flag-gated so a plan vs main = 0 until enabled). These are the agents
that drive the loops on a cadence (they complement, not replace, the EventBridge folds in Step 2).

---

## STEP 5 — Signal-generation follow-up (the honest gap)  `[agent — net-new code]`

Even fully live, the **machine** fidelity path stays mostly UNSCORED: a dogfood auto-responder has no
separate human "actual" per turn, so `shadow_prediction` pairs grade unscored (by design — never
fabricated). The live signal today is **human verdicts** (wired end-to-end). Two ways to add a machine signal:
1. **Candidate-extractor** (BUILT this session — pairs with the write-trigger `extract` seam): a Haiku
   pass decides "does this turn hold a durable fact + how confident", emitting a `memory_candidate` with
   an HONEST confidence so the **vault loop** gets live candidates. See PR `<candidate-extractor PR>`.
2. **LLM-as-judge over a later human turn**: when a human follows up in-thread, grade the NEop's prior
   `shadow_prediction.predicted` against that human turn as the `actual` (the judge is already wired in
   `fidelity_runner`; this needs the pairing logic that finds the later human turn). Follow-up build.
Provenance stays honest: `fidelity_breakdown` reports human-only vs machine/judge separately.

---

## STEP 6 — IAM (LAST — removes the agent's own access)  `[you]`

Do this **after** deploys/flips, via a break-glass-preserving migration:
1. Create the scoped `neos-agent-ops` role/user from the validated policy (`docs/security/
   agent-least-privilege-policy.attachable.json`, Access-Analyzer 0 findings; PR #137 open — review+merge).
2. Migrate the box's credential to it; **keep a human-held break-glass admin** (never a bare detach —
   self-lockout on live prod).
3. Deactivate `mansi-synlex` AdministratorAccess keys + rotate `bedrock-dev`.
Record the swapped-to principal ARN + date in `docs/security/README.md` (the pending fields).

---

# B. Broader roadmap (beyond Tracks 1/3) — sequenced

Not gated on Steps 1–6, but larger. From `technical-plan-3-month-2026-07.md` (§5) + `production-plan-
remaining-2026-07.md`. Legend: LIVE · WIRE (code exists) · APPLY (TF toggle) · IMAGE · NEW.

### Track 2 — Substrate & graph  `[you: the apply; agent: the wiring/images]`
1. **`enable_comms_tier=true`** (APPLY, riskiest — 29 resources: NATS/ClickHouse/Redis/RDS). Plan-first,
   zero-destroy gate, ONE conscious apply. Unblocks the durable event bus + audit-at-scale + fidelity
   writer→ClickHouse (retires the interim `run_events` palace store).
2. **Graph images** (IMAGE, agent): build+push real `bridge_image` (Graphiti L2) + `falkordb_image`
   (both literal `PLACEHOLDER` today); deploy the bridge task (EFS/ECR/access-point exist).
3. **4-backend RRF** (WIRE, agent): add BM25 + graph + recency channels server-side so `runtime/rrf.py`
   fuses 4, not 1 (vector-only today).
4. **`audit_emit.py` → ClickHouse sink** (WIRE, agent; after 1).
5. **Convex HA** (NEW-ish): SQLite-on-EFS single-writer → Postgres backend. Required before any 2nd tenant.

### Track 4 — Product surface  `[agent — the big NEW block]`
1. **nc-web** (NEW): React over `matrix-js-sdk` — channels/DMs/threads/optimistic render + twin/fidelity
   dashboard + Decision Queue (Promote/Edit/Reject) + nc-admin. Largest net-new; weeks via SDK reuse.
2. **Decision Queue MVP**: Matrix-room-+-reactions first (days) → nc-web panel later.
3. **Fidelity dashboard**: Grafana-over-ClickHouse (after Track 2 §1) → custom panel later.
4. **Interviewer seat**: deploy for onboarding (≤15-min, 80-Q → twin v0).
5. **Public front door**: flip `alb.tf`/`tls.tf` (HTTP-only in-VPC today) + federation. `[you: the flip]`
6. Streaming replies + non-Matrix adapters (Slack/Telegram/WhatsApp/Email) — demand-driven.

### Convergence / Day-90  `[calendar — needs a tenant]`
Onboard ≥5 real seats to twin v≥5 (Day 0) · cross-tenant red-team on a live 2nd palace + external
pen-test · fidelity ramp ≥0.65 over 90 days (fixed calendar) · 30-day zero-isolation window + S1–S9
gauntlet · full 4-layer ACL CI (Layer-2 = FalkorDB ⇒ depends on Track 2) · observability/DR (OTel→X-Ray,
Grafana, backups+restore drill, remote TF state, SLOs, status page) · compliance (DPDP required for V1,
SOC2 T1 path).

### Hygiene  `[agent — small, main-sync]`
Merge deployed-ahead infra PRs so main = live: **#107/#108/#109** (mergeable/clean), **#106** (rebase).
Touch `.tf` but deployed-ahead ⇒ merging is main-sync, **no apply** — review each diff vs live first.
Also **secrets → OS keychain** (off the chmod-600 `.env`) — a V1 blocker before user #2.

## The one gate that sets the date
Is there a **real tenant** for the first ≥5-seat deployment? Tracks 1–4 proceed on internal traffic with
no tenant, but Convergence (onboarding, 2nd-palace red-team, Day 0 of the 90-day clock) cannot start
without one. Per the plan, securing that tenant is the actual critical path — more than any build.
