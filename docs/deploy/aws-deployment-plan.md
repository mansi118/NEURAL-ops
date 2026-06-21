# NEOS — AWS Deployment Plan (to a live dogfood tenant, then V1)

**Honest frame:** "production-ready" is the **Day-90 acceptance gate** (≥5 seats, fidelity ≥0.65,
pen-test passed, 30d zero isolation violations) — inherently live + human, NOT agent-declarable. This
plan gets the system **deployed and dogfooding on AWS**; the Day-90 gate is earned in the live window
after. Each step is tagged **[A]** agent-buildable (I can do + verify offline / on self-host) or
**[U]** user-gated (AWS account, creds, paid services, sign-offs). `terraform apply` is always **[U]**.

The strategy is the one that's worked all along: **prove cheap, then commit infra.** The whole spine is
already live-proven on the self-host Convex backend; AWS is the same code on managed infra.

---

## Target architecture (dogfood tier)
```
            Internet
               │  (ACM TLS, 443)
          ┌────▼────┐
          │   ALB   │ public subnets
          └────┬────┘
        ┌──────▼───────┐   ECS Fargate, private subnets
        │ NEOS runtime │──► Convex (SoT)  ── Convex Cloud  [recommended]  OR  self-host on ECS+EFS
        │  (PiAgent)   │──► Embeddings   ── Bedrock Titan v2 (ap-south-1)  OR  self-host bge/e5
        └──────┬───────┘
               │ /external-denial, graph ops
        ┌──────▼───────┐
        │ Graphiti     │──► FalkorDB (Fargate + EFS persistence; advisory, can be down)
        │ bridge (L2)  │
        └──────────────┘
   Secrets Manager (values out-of-band) · CloudWatch · KMS CMK
   Phase 2: nc-channels (Matrix AS) + Synapse · nc-web (Decision Queue UI + dashboard)
```

---

## Phase A — Pre-flight: decisions + accounts  [U] (unblocks everything)
- [ ] **[U] Rotate the GitHub PAT** (30s — repos are clean, so rotation alone closes the transcript exposure).
- [ ] **[U] AWS account + a least-privilege Terraform deploy role** (creds in your shell, not in repo).
- [ ] **[U] Convex decision:** **Convex Cloud** (recommended for prod — managed durability + backups; `npx
      convex deploy` with `CONVEX_DEPLOY_KEY` → a `.convex.site` URL) **or** self-host the
      `convex-local-backend` on ECS+EFS. The functions are identical to what's live-proven on self-host.
- [ ] **[U] Embedder decision:** unblock **Bedrock Titan v2** (account-level click; `AWS_BEARER_TOKEN_BEDROCK`)
      **or** stand up self-hosted **bge/e5-large**. Retrieval is dark until this is chosen.
- [ ] **[U] Merge S0.1 PR #6** (runtime `Dockerfile` / `docker-compose` / `entrypoint` / boot self-check) —
      your docker review. This is the image Terraform's `runtime_image` expects.

## Phase B — Agent-buildable deployment prep  [A] (I do these; verified offline / self-host)
- [ ] **[A] Close the edge-emit gap** (the named 4th audit layer): a tenant-name→`palaceId` resolver at the
      edge seam, then `audit_emit.emit_external_denial(palaceId,"edge",…)` — so all 4 layers emit before live.
- [ ] **[A] Extend Terraform beyond the runtime tier:**
      - ECR repositories (runtime + bridge); image-build CI (GitHub Actions → ECR).
      - Bridge + FalkorDB task defs / services; **EFS** for FalkorDB persistence.
      - TLS: ACM cert + 443 listener + HTTP→HTTPS redirect (variable-gated on a domain).
      - Thread the runtime/bridge env + secret refs (`CONVEX_SITE_URL`, `ANTHROPIC_API_KEY`, embedder key,
        `PALACE_BRIDGE_API_KEY`, `BRIDGE_IDENTITY_ENABLED`, `CONVEX_DENIAL_SINK_URL`).
- [ ] **[A] Governance-flip as config, not code:** wire the orchestrator to construct
      `ApprovalBroker(policy, store=ConvexSnapshotStore(...))` when a policy is configured — so the flip is
      env/policy toggles (the seam is already live-proven).
- [ ] **[A] Deployed-stack E2E smoke:** point `tools/live_e2e_process.py` + the dogfish ACL smoke at the
      deployed ALB URL (the same proofs that pass on self-host, now against AWS).

## Phase C — Deploy  [U runs apply; A prepares + verifies]
1. [ ] **[A]** Build + push runtime & bridge images to ECR (CI or `docker build` + push).
2. [ ] **[U]** `terraform init && terraform plan -out tf.plan && terraform apply tf.plan` (the gate — AWS creds).
3. [ ] **[U]** Set secret VALUES: `aws secretsmanager put-secret-value …` for each `managed_secret_keys`
      (never in TF state). Generate `PALACE_BRIDGE_API_KEY` = `openssl rand -hex 24` (replace the dev
      `test-bridge-secret-123` used in self-host proofs).
4. [ ] **[U/A]** Deploy Convex (Cloud: `convex deploy`; or roll the self-host image) → set `CONVEX_SITE_URL`.
5. [ ] **[U]** `aws ecs update-service --force-new-deployment` (pick up images + secrets).
6. [ ] **[A]** Verify: `curl https://<alb>/health` → 200; run the deployed-stack E2E smoke; confirm
      `denialsByLayer` populates (all 4 layers) and a paused run round-trips the Decision Queue.

## Phase D — Activate + onboard  [U + A]
- [ ] **[U]** Flip governance: `BRIDGE_IDENTITY_ENABLED=true`, `CONVEX_DENIAL_SINK_URL` set, a minimal
      approval policy signed off (recommend `plan:ask` + `bash`/`browser`/`swarm`:`ask`, else `allow`).
- [ ] **[A/U]** Run the **Interviewer** for seat 1 → `twin.md` v0 (per-user, keyed by requester).
- [ ] **[U]** Onboard ≥5 dogfood seats; ≥3 NEops/seat in regular use.
- [ ] **[A]** Watch: `denialsByLayer` (target 0 isolation violations), the fidelity clock (per-user twin).

## Phase E — Production hardening → the Day-90 gate  [mostly U, some A]
- [ ] **[U]** KMS CMK (Secrets + logs) · remote TF state (S3 + DynamoDB lock) · domain/DNS/TLS · WAF ·
      autoscaling · multi-AZ NAT.
- [ ] **[A]** nc-web UI over the Decision-Queue API + dashboard over `denialsByLayer`; nc-channels Matrix
      adapter. **[U]** Synapse homeserver(s).
- [ ] **[A]** OTel instrumentation + CloudWatch alarms/SLO dashboards.
- [ ] **[U]** Pen-test (red-team isolation) · DR drill (backup/restore).
- [ ] **[U]** The **Day-90 acceptance window** — the live measurement that *is* "production-ready".

---

## Critical path (shortest line to a live dogfood tenant)
`[U] PAT + AWS creds + Convex Cloud + embedder choice + merge #6`  →  `[A] Terraform extend + ECR + flip-as-config + edge-emit`  →  `[A] push images` → `[U] terraform apply + secrets` → `[A] verify on the deployed stack` → `[U] flip governance + onboard`.

**What only you can do:** the AWS account/creds, the `terraform apply`, the paid/managed services (Convex
Cloud, Bedrock, Synapse), secret values, policy sign-off, pen-test, and the live tenant + 30-day window.
**What I can do now (Phase B):** everything that doesn't need an AWS account — extend the IaC, close the
edge-emit gap, make the flip a config toggle, and prepare the deployed-stack smoke — all verified on the
self-host before your apply. Say go and I'll start Phase B.
