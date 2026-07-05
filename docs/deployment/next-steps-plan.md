# NEOS — Next-steps execution plan (resume from here)

> Companion to `session-checkpoint-2026-07-05.md`. That doc = **verified state**; this doc = **what to do
> next, in order, with gates and owners.** `[A]` = agent-doable · `[ML]` = your gate (key/apply/access/OK) ·
> `[BOX]` = proven live, never faked offline. Nothing here is "final deployment" as a single act — it's a
> sequence to the three Bars; most of the critical path is `[ML]` gates.

## 0 · Restore context (read first, in a fresh session)
1. Read `docs/deployment/session-checkpoint-2026-07-05.md` — the resolved state (both scares grounded).
2. **Verified facts (don't re-derive):** account `071126865245`/ap-south-1.
   **⚠️ LOADED FACT — hold with its teeth:** this WSL box **has live creds + Docker + TF** (CLAUDE.md's "no
   creds" is stale). This is the single most dangerous fact here — it's what made the misdirected apply
   possible (live creds + a trusted-but-wrong tfstate → a redundant Synapse on the real account). **Every
   `terraform apply`/`destroy` from here hits production `071126865245` for real, with no dry-run cushion.**
   So plan-first + read-before-mutate is not hygiene here, it's the *only* thing between a command and an
   irreversible production change. Record the capability WITH the caution, or a fresh instance inherits the
   power without the lesson. Live spine = **ECS Fargate** (convex/runtime/bridge, VPC `10.40`,
   internal). Palace `/mcp` = `convex.neos-dogfood.local:3211` (in-VPC only). `matrix.neuraledge.in` = **real
   EC2 Synapse 1.150.0** (default VPC `172.31`). **Embedder healthy** (Titan-v2, 26/26 embedded). Ranking
   **unproven**. `Mempalace_NEOS` cloned+`npm ci`'d at `/mnt/c/Users/LENOVO/Desktop/Mempalace_NEOS` (HEAD #29).
3. **How to run a tool in-VPC** (the palace is internal): adapt `infra/build/spine-verify.sh` (on main) —
   bundle `neural-ops` (`tools/ runtime/ frontdoor/ ...`) + `Mempalace_NEOS`, upload to
   `neos-dogfood-codebuild-src-*`, `aws codebuild start-build --project-name neos-dogfood-spine-verify
   --source-location-override <zip> --buildspec-override <spec>` where `<spec>` runs your `tools/*.py` with
   `NEOS_SMOKE_{API,SITE,ADMIN}_URL` + `MEMPALACE_DIR` env. Tools are on main: `tools/{ranked_retrieval_proof,
   aria_inspect,palace_status_check}.py`. (The scratchpad runners from last session are gone; reconstruct from
   spine-verify.sh — it's ~15 lines of delta.)

## Track A — Prove RANKING (Bar-2 prerequisite) · IMMEDIATE · closes the write-persistence question too
Read the rerun **two-part: persistence THEN ranking** (checkpoint §BANK). One run resolves both.
- **A1 `[ML]`** — Approve seeding **one throwaway, obviously-synthetic permissioned seat** for the canary
  (the ranked write is ACL-denied on unseeded seats; no designated test seat exists). This is a **`seed:access`
  ACL mutation** — scope to one seat, e.g. `zzz-canary-<synthetic>`, perms `[recall, remember]` only.
- **A2 `[A]`** — Seed that seat (scoped mutation via `config/access_matrix.yaml` + `npm run seed:access`, or a
  targeted `neop_permissions` insert), verify it exists, nothing else changed.
- **A3 `[A]`** — Run `tools/ranked_retrieval_proof.py` in-VPC against the seeded seat (edit `SEAT=` to it).
- **A4 `[A]` — the read (four-way, one layer earlier):**
  (i) **persistence** — did the canary write land as a **durable retrievable closet**? (the aria smoke write
  did NOT — check explicitly). No-persist ⇒ the **write-quarantine finding is now the priority** (understand
  why writes no-op before ranking means anything).
  (ii) **ranking** — canary at **rank-1** on the oblique query, score **≥ ABS_MIN** (pin from the oblique
  landing), **graceful-empty = FAIL**. Persist+mis-rank ⇒ the **#30 gap**. Persist+rank ⇒ **both close.**
- **A5 `[A]`** — Clean up: retract the canary closet (now you have a real by-ID target → `retractCloset`) +
  remove the throwaway seat's perms. Leave the palace as found.
- **Outcome:** ranking proven (Bar-2 foundation) OR a real finding (write-quarantine / mis-rank) surfaced now.

## Track B — Matrix front door → Bar 1 (echo through real Synapse) · parallelizable with A
- **B1 `[A]` (offline, do now)** — **Cross-VPC placement design doc.** `nc-channels` runs the orchestrator
  in-process (needs the public Synapse in default-VPC AND the palace `/mcp` in spine-VPC). Fork: **on the
  `matrix-server` box** (Synapse=localhost; palace hop needs default↔spine peering/route) vs **in the spine
  VPC** (palace=internal; Synapse needs a reachable inbound to nc-channels). Decide + record; palace is now
  proven reachable+functional in-VPC.
- **B2 `[ML]`** — **AS-registration on the production homeserver** using `docs/deployment/as-registration-runbook.md`
  (#79): SSH to `matrix-server`, mint `as_token`/`hs_token` (`openssl rand -hex 32`), **read current
  `homeserver.yaml` → BACKUP → ADDITIVE edit `app_service_config_files` → restart → verify existing traffic
  → rollback known first.** Your hands, not the agent's (production, served since April).
- **B3 `[BOX]`** — Build `serve()`/`_cs_api_call` against **real Synapse**, hand-driven first (one CS-API call
  at a time), then wrap in `serve()`. Never faked offline. (`nc_channels/service.py:119/125`.)
- **B4 `[ML]`** — Deploy `nc-channels` per the B1 placement decision (its own service; the held Fargate
  `nc-channels.tf` targeted a synapse that's now retired — re-target to `matrix.neuraledge.in`).
- **B5 `[LIVE]`** — Create `@neos-bot` + a seat + room → Element (over SSM tunnel or public) → **round-trip =
  Bar 1** (echo; canned until Bar 2). Acceptance: `@neop_*` reply appears; no `_admin` bypass.

## Track C — Bar 2 (memory-backed reply) · after A green + B live
- **GAP-1** — port the `/mcp` contract from `neop_jcode_adapter/palace_mcp_shim.py:20-24` into
  `pi-neop-runtime/src/brokers/memory.ts:23` (scope-baked, fail-closed). **Needs that repo checked out `[ML]`.**
  Acceptance = `tools/ranked_retrieval_proof.py` shape (already your validated harness).
- **GAP-2** — containerize Hermes/Node under the T7 egress-jail spec (validate against the Node model). Then
  **M1b** (runtime serves a seat live) → the Matrix reply becomes memory-backed.

## Track D — Bar 3 (`nc-web` product UI) + production-ready · far
- `nc-web` = a multi-week frontend build (Matrix client on the seat rooms + app-plane dashboard), not started.
- Production-ready = the 90-day fidelity clock (≥5 seats, fidelity ≥0.65 over rolling 30d, pen-test, 6
  meta-NEops live). Can't start until ≥5 seats are live.

## The `[ML]` gates on the critical path (nothing moves without these)
1. **Seed-seat approval** (A1) — unblocks the ranked proof.
2. **Box access to `matrix-server`** (B2) — unblocks Matrix registration → Bar 1.
3. **`pi-neop-runtime` checkout** (C/GAP-1) — unblocks Bar 2.

## Recommended order for the next session
1. **B1** (placement design — offline, no gate) while waiting on A1.
2. **A1→A5** (ranked proof) the moment you OK seeding the throwaway seat — one run closes ranking + persistence.
3. Then **B2→B5** (the Matrix box window) when you're ready to sit it, on now-verified ground.
Do **not** collapse steps or fake a green; every layer read for what it proves. "Final deployment" is Bars
1→2→3 then the 90-day clock — this plan gets you to **Bar 1 on verified ground**, with 2 and 3 sequenced honestly behind it.
