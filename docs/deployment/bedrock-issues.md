# Bedrock — DevOps handoff / open issues

> **For:** the DevOps/cloud engineer provisioning the NEOS model path.
> **Context in one line:** NEOS's runtime LLM is **Bedrock Nova, invoked in-VPC over the sealed spine** (no NAT;
> deploy-topology "Decision 2"). The wrapper/runtime reaches `bedrock-runtime.ap-south-1.amazonaws.com` via a
> **PrivateLink interface endpoint** and authenticates with a **bearer token** (`AWS_BEARER_TOKEN_BEDROCK`),
> which **bypasses SigV4/IAM**. Everything below is about making that one path work end-to-end.
> **Account:** `071126865245` · **Region:** `ap-south-1` (the spine region — this matters, see #1).
> **Status legend:** ✅ confirmed working · ⚠️ needs action · ❓ unverified (please check).

---

## ✅ Already confirmed (do NOT spend time re-checking these)
Verified read-only 2026-07-08 against the live account:
- **Nova is access-granted.** `aws bedrock get-foundation-model-availability --model-id amazon.nova-lite-v1`
  → `authorizationStatus: AUTHORIZED`, `agreementAvailability: AVAILABLE`, `entitlementAvailability: AVAILABLE`,
  `regionAvailability: AVAILABLE` in `ap-south-1`. **Model access is not the problem.**
- **The PrivateLink endpoint exists.** `infra/terraform/endpoints.tf` provisions the `bedrock-runtime` interface
  VPC endpoint with `private_dns_enabled = true`; the `vpce` SG allows `443` from the VPC CIDR. So in-VPC,
  `bedrock-runtime.ap-south-1.amazonaws.com` resolves to the endpoint (no NAT needed).
- **The embedder path (Titan) already works in-VPC via bearer** — the historical proof the same bearer+
  PrivateLink path serves Bedrock (Titan embeddings). Nova (generation) rides the *same* path.

---

## ⚠️ #1 — Provision an **ap-south-1-scoped** bearer token (THE primary blocker)
Nothing live runs without this. `AWS_BEARER_TOKEN_BEDROCK` must be:
- **Region-scoped to `ap-south-1`.** A **us-east-1 token 403s against ap-south-1** (tested 2026-07-08 — the
  spine is ap-south-1). This is the single most common failure; the token's `X-Amz-Credential` scope must read
  `…/ap-south-1/bedrock/…`.
- **Provisioned into two places:**
  1. **The deployed Convex** (for ingestion extraction — see #5, the write-quarantine fix). Check with
     `npx convex env list` / `convex env get AWS_BEARER_TOKEN_BEDROCK` on the deployed deployment.
  2. **The wrapper task** (when `enable_wrapper=true`) — as a Secrets Manager secret reference
     (`infra/terraform/wrapper.tf` wires `AWS_BEARER_TOKEN_BEDROCK` as a required secret; set its value with
     `aws secretsmanager put-secret-value`, never inline).
- **Identity permissions for the token** (see #2).
- Tokens are typically short-lived (the ones used in testing were ~12h presigned). Decide whether to use a
  long-lived Bedrock **API key** or automate refresh — a 12h token is not a durable production credential.

## ⚠️ #2 — The bearer token's identity needs `InvokeModel` on Nova (NOT the task role)
This is the subtle one. **The bearer bypasses SigV4**, so the ECS **task role's** Bedrock policy is NOT what
authorizes a Nova invoke:
- `infra/terraform/iam.tf:54-55` — the task role's `bedrock:InvokeModel` is scoped to
  **`amazon.titan-embed-text-v2:0` ONLY** (Titan embed). It deliberately does **not** include Nova. So a
  SigV4/task-role Nova invoke would be **AccessDenied** — but the runtime doesn't use that path.
- **What actually authorizes the Nova invoke:** the **bearer token's own identity** needs
  `bedrock:InvokeModel` on the Nova model + `bedrock:CallWithBearerToken`. ❓ **Confirm the identity that mints
  the bearer has `InvokeModel` on `apac.amazon.nova-lite-v1:0` (and `CallWithBearerToken`).**
- ⚠️ **If you instead intend the task role to invoke Nova via SigV4** (no bearer), then `iam.tf`'s
  `bedrock_invoke` must be widened to include the Nova model ARN — currently it's Titan-only.

## ⚠️ #3 — Use the **APAC inference profile** model id, not the bare id
On-demand invoke of Nova needs the **regional inference profile**: **`apac.amazon.nova-lite-v1:0`**. The **bare**
`amazon.nova-lite-v1:0` **rejects on-demand** (`ValidationException` / "invocation with on-demand throughput
isn't supported; use an inference profile"). The runtime already defaults to the `apac.*` id; just ensure any
manual test / IAM resource ARN uses the `apac.*` profile, and that the profile is enabled in `ap-south-1`.

## ⚠️ #4 — The dev IAM user (`mansi-synlex`) can't invoke Bedrock or run the verify
`mansi-synlex`'s only Bedrock grant is `BedrockModelAccess` = `PutUseCaseForModelAccess` /
`GetUseCaseForModelAccess` / `ListFoundationModels` / `GetFoundationModelAvailability` — the model-access-*form*
and *listing* actions. It has **no `bedrock:InvokeModel`**, and **no** `codebuild:StartBuild` / `iam:PutRolePolicy`
/ `ec2:*` / `s3:*` write. Consequence:
- The in-VPC verification (`infra/build/spine-verify.sh`, a VPC-attached CodeBuild) **cannot be triggered by
  `mansi-synlex`** — it needs `codebuild:StartBuild`/`CreateProject`/`UpdateProject`, `iam:PutRolePolicy`,
  `ec2:CreateSecurityGroup`, `s3:PutObject`.
- ⚠️ **Action:** run the verify with a role/user that has those (your CI/admin role), **or** deliberately widen
  `mansi-synlex` (or a dedicated role) with `bedrock:InvokeModel` + `codebuild:StartBuild` if you want it
  self-serviceable.

## ⚠️ #5 — Confirm the write-quarantine fix is live (Convex extraction)
Background: NEOS memory writes were silently **quarantining** — the ingestion extraction step's model call was
failing (Gemini unreachable from the no-NAT spine → `extraction_failed: fetch failed`). The fix is the same
Bedrock-Nova-in-VPC path (`Mempalace_NEOS/convex/lib/bedrockLlm.ts`, `convex/ingestion/extract.ts`).
- ❓ **Verify:** is `AWS_BEARER_TOKEN_BEDROCK` (ap-south-1) set in the **deployed** Convex env, and does a test
  write **extract + persist** (not quarantine)? A green here confirms the model path live AND fixes the writes.
- The existing `neos-dogfood-embedder-verify` CodeBuild (`infra/build/buildspec-embedder-verify.yml`) exercises
  the in-VPC Bedrock path with the bearer — a good first smoke.

---

## How to verify the path end-to-end (in-VPC — the only place it can be proven)
The whole point is **in-VPC**: from a laptop/dev box, `bedrock-runtime.ap-south-1` resolves to the *public*
endpoint, which does NOT prove the sealed-spine path. Run these on a **VPC-attached** runner (CodeBuild in the
private subnets, or an in-VPC EC2/task):

1. **Bedrock reachability + auth (Titan, cheapest):** trigger `neos-dogfood-embedder-verify` with the
   ap-south-1 bearer set. Green = PrivateLink + region + bearer identity all work.
2. **Nova generation (the actual model path):** an in-VPC `InvokeModel` against
   `apac.amazon.nova-lite-v1:0` with the bearer:
   ```
   curl -s -X POST \
     "https://bedrock-runtime.ap-south-1.amazonaws.com/model/apac.amazon.nova-lite-v1:0/invoke" \
     -H "Authorization: Bearer $AWS_BEARER_TOKEN_BEDROCK" \
     -H "Content-Type: application/json" \
     -d '{"system":[{"text":"Reply with the word ALIVE."}],"messages":[{"role":"user","content":[{"text":"go"}]}],"inferenceConfig":{"maxTokens":16}}'
   ```
   (This mirrors `Mempalace_NEOS/convex/lib/bedrockLlm.ts`.) A clean completion = the model path is live.
3. **Ranked memory (needs Convex admin key, not the bearer):** `neos-dogfood-spine-verify` →
   `tools/ranked_retrieval_proof.py` (override the buildspec) — but this needs a **permissioned seat**
   (a `seed:access` ACL grant), which is an application-side gate, not pure DevOps.

## Diagnosing a failed Nova invoke (the four named causes)
If step 2 fails, it's one of:
- **`403` / auth** → the bearer is invalid or **wrong region** (us-east-1 token in ap-south-1 — #1), or the
  bearer's identity lacks `InvokeModel`/`CallWithBearerToken` (#2).
- **model-not-granted / ValidationException** → using the **bare** id instead of `apac.*` (#3). *(Model access
  itself is AUTHORIZED — see the ✅ section — so this is the profile id, not account access.)*
- **connection refused / DNS / timeout** → not actually in-VPC, or the SG/PrivateLink path is wrong (the runner
  can't reach the `bedrock-runtime` endpoint).
- **wrong-region** → the request didn't target `ap-south-1`.

---

## Summary checklist for DevOps
- [ ] Mint/provision an **ap-south-1** `AWS_BEARER_TOKEN_BEDROCK` (not us-east-1) — decide durable key vs 12h refresh. **#1**
- [ ] Confirm the bearer identity has `bedrock:InvokeModel` (on `apac.amazon.nova-lite-v1:0`) + `CallWithBearerToken`. **#2**
- [ ] Set the bearer in the **deployed Convex** env; verify a write extracts + persists (no quarantine). **#5**
- [ ] Set the bearer as the wrapper's Secrets Manager value when `enable_wrapper=true`. **#1**
- [ ] Run the in-VPC Nova invoke test (step 2) — confirm a real completion. **verify**
- [ ] (If self-serve desired) widen a role with `bedrock:InvokeModel` + `codebuild:StartBuild`. **#4**
- [ ] Ensure any manual test / IAM ARN uses the **`apac.*`** profile id. **#3**
