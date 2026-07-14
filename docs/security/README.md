# Agent least-privilege replacement role (proposal)

The agent operates the box as IAM user `mansi-synlex`, which currently carries
**AdministratorAccess**. That is the longest-open, highest-priority security exposure: a live
administrator credential on an agent-operated box, on a system about to run live NEops in real seats.

Two files:
- `agent-least-privilege-policy.json` — the **annotated** proposal (with `//` comment keys explaining each
  statement). IAM does **not** accept `//` keys, so this is documentation, **not** directly attachable.
- `agent-least-privilege-policy.attachable.json` — the **attachable** version (comments stripped).
  Validated with IAM Access Analyzer (`validate-policy`, IDENTITY_POLICY): **0 findings** — no errors, no
  security warnings. Attach THIS one.

Both are a **proposal** for a scoped replacement, derived from the AWS actions the agent has **actually**
used — not from assumption. Division of labour:

- **Agent designs the scoped role** (this doc). It cannot and must not remove its own operating credential.
- **You (ML) review + execute the IAM swap**: detach AdministratorAccess from `mansi-synlex` (or move
  the box to a dedicated role) and attach this policy. The swap is an IAM/console action, yours.

## Why scope from real calls (two evidence-backed reductions)

- **No Bedrock invoke.** Every generative call went through the `bedrock-dev` **bearer token**, not this
  identity (the Converse smoke even ran with admin keys unset). So the role needs Bedrock **read** only —
  a real reduction you'd have over-granted if scoping from "it does model calls."
- **SSH-rule management scoped to ONE security group** — the matrix box SG (`sg-0c7a71c257e07eb9a`), never
  the palace/spine SGs. The scoped role structurally **cannot** open the palace or spine firewalls.

## The structural guardrail

The policy **excludes** `iam:*` writes, any `*:*`, and broad terraform-apply permissions. Production
`terraform apply` stays a **gated, separately-elevated manual step** — it is not something the everyday
agent identity carries. That encodes the read-only-on-prod boundary into **IAM** rather than relying on
the agent's restraint: a role that *cannot* apply cannot be drifted into applying.

## One deliberate decision for review

The **S3 `PutObject` + CloudFront invalidation** (nc-web deploy) permissions are **flagged, not granted**.
Decide consciously: grant them **scoped to the specific bucket + distribution** (not `s3:*`) only if the
agent will perform nc-web deploys, or leave them out and add them when a deploy actually needs them. Do
not let "the deploy script uses them" auto-expand into a broad S3 grant.

## After the swap

Record the role/policy actually swapped to here (ARN + date), so the proposal and the executed state stay
linked:

- Swapped-to principal: _(pending — record after the IAM swap)_
- Date / by: _(pending)_
