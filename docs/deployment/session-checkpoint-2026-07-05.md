# Session checkpoint — 2026-07-05 (reset-proof)

> Engineering state at a deliberate stop (~82% context). Nothing in production was touched; the delete
> gate held through the whole session and resolved to a no-op. A fresh instance should inherit the
> **honest** state below, not an optimistic one.

## ✅ RESOLVED this session (both scares grounded — read this, don't re-run the CodeBuilds)
- **Embedder health = HEALTHY** (`b9siqptdf` landed). `degraded=false`, provider `bedrock-titan-v2`,
  **26/26 closets embedded**, 0 failed, 0 pending, `reason=ok`. ⇒ The "degraded embedder" hypothesis is
  **falsified**, and this **retroactively validates the 7/7 smoke**: retrieve wasn't passing on a dead
  embedder. "Spine responds" is trustworthy now.
- **`aria` was NOT polluted.** Palace stats: **26 closets, retracted=0, decayed=0**, newest memory **4 days
  old** (the smoke ran minutes ago → if it had persisted, "recent" would read today). Retrieval for the exact
  smoke content returns 0. ⇒ The smoke's `broker.write` to `aria` **quarantined/no-op'd — never created a
  closet.** No cleanup, no retract. The delete gate resolved to a clean no-op.
- **3-vs-0 retrieval discrepancy** = floor-filtering + query-sensitivity (26 embedded closets exist; test
  queries scored below the 0.35 similarity floor). Not a fault.

## 🧾 BANK (a narrow-green to understand later, do NOT chase now)
`broker.write` to `aria` **reported success at the smoke layer** (7/7 counted it PASS on
`status in ok/partial/quarantined/noop`) but **never persisted a retrievable closet**. Same *class* as
graceful-empty retrieve — a green narrower than it looks. If real writes can silently quarantine, that's a
**Bar-2 concern**. File it; understand the quarantine/no-op path eventually.

## 🔒 DELETE GATE (verbatim — must survive reset intact)
No `retractCloset` runs until ALL: (a) DB closet count reconciles; (b) smoke write **positively identified by
its own content** `"smoke: deployed-stack check"`; (c) **real non-null `closetId`**; (d) **human confirms
that specific ID**. Null-id chunks or ambiguous content = **stop-and-report, not delete.** (This session it
resolved to: nothing to delete.)

## 📊 HONEST FOUNDATION HEADLINE (use this, not the optimistic one)
> Spine **write / ACL (fail-closed, confirmed live ×2) / decision-queue / twin** verified end-to-end in-VPC.
> **Embedder healthy** (Titan-v2, 26/26 embedded). **Retrieve proven to respond** (7/7, real embedder
> confirmed). **Ranking still UNPROVEN** — the ranked proof's canary write was ACL-denied on an *unseeded*
> seat (test-design flaw, not a spine result). **Matrix Bar 1 foundation = solid. Bar 2 = gated on the
> ranked proof.**

## ✅ MERGED & SOLID (ground a reset can build on)
- Fargate comms-tier **reverted** (runtime spine `convex/runtime/bridge` untouched, 1/1 healthy, verified).
- **ADR #77** — canonical homeserver = **existing EC2 `matrix.neuraledge.in`** (real Synapse 1.150.0; TLS +
  federation + `.well-known` live). Fargate `synapse.tf` retired for Matrix.
- **#78** — `synapse.tf` **structurally disarmed** (`local.synapse_enabled = enable_comms_tier &&
  enable_fargate_synapse`, the latter default-false/set-by-nothing). `phase2` plan = 19 adds, **0 Synapse**.
- **#79** — AS-registration runbook (cold; regex `@neop_.*:matrix\.neuraledge\.in` bound to the live
  `server_name`; backup → additive edit → restart → rollback). Tokens + `url` are the only blanks.
- CodeBuild `s3:ListBucket` IAM fix (scoped to the one source bucket; CodeBuild is out-of-band, not TF).

## 🗂️ ENVIRONMENT FACTS (verified, don't re-derive)
- Account `071126865245`, ap-south-1. This WSL box HAS live creds + Docker + terraform 1.9.8 (CLAUDE.md's
  "no creds/no Docker" is STALE).
- Live spine = **ECS Fargate** (convex/runtime/bridge), VPC `10.40/16`, internal (Cloud Map, no public ALB
  target → ALB 503 by design). `matrix-server` EC2 (Synapse) is in the **default VPC 172.31/16**.
- Palace = `convex.neos-dogfood.local:3210` (API) / `:3211` (`/mcp` site), internal → all functional tests
  run **in-VPC via CodeBuild** (project `neos-dogfood-spine-verify`, buildspec-override + bundle).
- `Mempalace_NEOS` cloned + `npm ci`'d at `/mnt/c/Users/LENOVO/Desktop/Mempalace_NEOS` (HEAD **#29**).
- In-VPC test mechanics: `scratchpad/run-*.sh` + `buildspec-*.yml` (smoke-only / ranked / aria / status).
  The tools bundle from `tools/` (now committed — see below).

## 📋 NEXT SESSION — in order (no embedder branch anymore; it's healthy)
1. **Ranked proof rerun** (Bar-2 prerequisite; `tools/ranked_retrieval_proof.py` is the GAP-1 harness). Needs
   a **permissioned seat** — the canary write is ACL-denied on unseeded seats. **No designated test seat
   exists** (seeds: aria/recon/icd/cos/nexus/alte/forge/scout/emma/neuralchat/teampulse/_admin). So: seed a
   **throwaway obviously-synthetic permissioned seat** via `seed:access` — **this is an ACL mutation; name it,
   scope to one seat, ask ML first, clean up after.** Full GAP-1 bar (oblique query, rank-1, ABS_MIN from the
   oblique score, graceful-empty=FAIL). Now easier: 26 real embedded memories exist to test against.
2. **Matrix front door.** ML runs AS-registration from **#79** (read current `homeserver.yaml` → backup →
   **additive** edit → restart → rollback known first). Then the **cross-VPC `nc-channels` placement** design
   (on the `matrix-server` box [Synapse=localhost, palace needs peering] vs in the spine VPC [palace=internal,
   Synapse needs reachable inbound]) — the palace is now proven reachable+functional in-VPC.

## Session read (plain)
Value was catching what **wasn't true** before it hid downstream: Fargate redundancy (real → reverted),
tfstate-vs-reality drift (real → ADR'd + disarmed), embedder scare (falsified), aria pollution (falsified),
ranking (honestly still open, not faked). Real ones fixed durably + made un-repeatable; false ones proven
false, not assumed. Delete gate held → no-op. Every green read for what it proved. Bar 1 not shipped, but its
foundation is now real ground.
