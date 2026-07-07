# ModelBroker Bedrock provider — design (faithful port against a proven mechanism)

> The code half of Decision 2 (`deploy-topology-design.md`): give `pi-neop-runtime`'s `ModelBroker` a
> **Bedrock (Nova) provider**, so the wrapper generates in-VPC over the sealed spine (no NAT). Scopeable
> today because the mechanism is proven; the deployed-live + region-matched-token confirmations are box-verifies.

## ✅ IMPLEMENTED — 2026-07-07 (`mansi118/pi-neop-runtime#8`)
Landed as a faithful ~40-line wiring in `src/brokers/model.ts` (+6 offline tests, 84/84 green, `tsc` clean).
**The one open box-verify's _direction_ is now resolved at the SOURCE level** (traced pi-ai dist):
- pi-ai sends `model.id` **verbatim** as the Converse `modelId` (`amazon-bedrock.js:98`) — there is **NO**
  region→`apac.*` derivation. And `getModel` returns `undefined` for off-catalog ids (registry holds only bare
  nova ids). ⇒ the profile **must be stamped onto `model.id`**: fetch the bare catalog `Model`, set
  `model.id = "apac.amazon.nova-lite-v1:0"`.
- bearer **and** region are read from env by pi-ai itself (`bearerToken || AWS_BEARER_TOKEN_BEDROCK`;
  `region || AWS_REGION || AWS_DEFAULT_REGION`) ⇒ `getApiKey` is moot (delta #2 confirmed at source); the
  broker **pins `ap-south-1`** instead (the token is region-scoped).
**What remains box-side** is narrowed to a single live fact: does the stamped `apac.*` profile + an
ap-south-1 bearer actually **generate in-VPC**. resolves ≠ generates.

## Why this is a small, faithful change (not a from-scratch integration)
- **pi-ai already supports Bedrock with bearer-token auth + Nova.** Verified in its dist: `bedrock` (390×),
  `AWS_BEARER_TOKEN_BEDROCK` (3×), `converse` (90×), `nova`/`amazon.` refs. So Bedrock-Nova can be a real
  `ModelBroker` provider that the pi Agent consumes as a `Model` — **no pi-Agent bypass** (both the Generate
  path AND the task path get Bedrock).
- **`Mempalace_NEOS/convex/lib/bedrockLlm.ts` is the working reference** (verified in-VPC 2026-06-29): endpoint
  `bedrock-runtime.<region>/model/apac.amazon.nova-lite-v1:0/invoke`, `Authorization: Bearer <AWS_BEARER_TOKEN_BEDROCK>`,
  Nova body `{system, messages, inferenceConfig}`. The provider maps THIS into pi-ai's interface.

## Primary path (P1) — add `bedrock` to `ModelBroker` (`src/brokers/model.ts`)
Transcription against the existing provider machinery (`resolveLiveModel` is already provider-generic —
`registryGetModel(provider, wanted)`):
```ts
export const PROVIDER_KEY_ENV = {
  anthropic: "ANTHROPIC_API_KEY",
  openrouter: "OPENROUTER_API_KEY",
  bedrock:   "AWS_BEARER_TOKEN_BEDROCK",   // + NEW
};
const DEFAULT_MODEL = {
  anthropic: "claude-sonnet-4-6",
  openrouter:"anthropic/claude-haiku-4.5",
  bedrock:   "apac.amazon.nova-lite-v1:0", // + NEW (APAC inference profile; bare amazon.nova-* rejects on-demand)
};
```
- **Provider selection:** set `NEOP_PROVIDER=bedrock` for the wrapper (do NOT change the global
  `DEFAULT_PROVIDER` — that would break unit-mode expectations). `resolveProvider` already reads `NEOP_PROVIDER`.
- **Fail-closed inherited:** `resolveLiveModel` already throws if `PROVIDER_KEY_ENV[provider]` env is unset
  (`model.ts:159-163`) → blank `AWS_BEARER_TOKEN_BEDROCK` refuses at construction. No new fail-open surface.
- **In-VPC networking is DNS, not config:** in the spine, `bedrock-runtime.ap-south-1.amazonaws.com` resolves
  to the PrivateLink via the `endpoints.tf` private-DNS override — so no `baseUrl` override; the default
  hostname reaches the endpoint (same as `bedrockLlm.ts`).

## REGISTRY VERIFIED (2026-07-07) — deltas #1/#2/#4 resolved; only a bare-vs-profile box-verify remains
Traced pi-ai's dist:
- **Provider key = `"amazon-bedrock"`** (pi-ai `KnownProvider` type), NOT `"bedrock"`. So
  `registryGetModel("amazon-bedrock" as any, <id> as any)` (the broker already casts `as any`).
- **Bearer (delta #2 resolved):** `BedrockOptions.bearerToken` — *"When set, bypasses SigV4 and sends
  Authorization: Bearer <token>. Set via `AWS_BEARER_TOKEN_BEDROCK` env var."* pi-ai reads the exact env; the
  bearer flows without `getApiKey` (document that asymmetry — `getApiKey` is moot for this provider).
- **Region (delta #3):** `BedrockOptions.region?` exists → set `ap-south-1`.
- **Nova format (delta #4 resolved):** streams via `bedrock-converse-stream` (the Converse API) → Nova-native.
- **Model ids:** pi-ai's registry knows `amazon.nova-lite-v1:0` / `nova-micro` / `nova-pro` / `nova-2-lite`
  (**bare** ids). **THE ONE REMAINING NUANCE / BOX-VERIFY:** on-demand invoke needs the **`apac.*` inference
  profile** (bare `amazon.nova-*` rejects on-demand — proven by `bedrockLlm.ts` + probe). So either pi-ai's
  `region` option maps the bare id → the regional profile internally, OR pass `apac.amazon.nova-lite-v1:0`
  directly (the `as any` cast allows it). **Box-verify which form pi-ai accepts + resolves in-VPC** — this is
  now the *only* open code question; everything else is settled.

## THE DELTAS FROM THE REFERENCE — read these closely (a faithful port's risk lives here)
1. **pi-ai's exact provider-key + model-id form.** Confirm `registryGetModel("bedrock",
   "apac.amazon.nova-lite-v1:0")` resolves — pi-ai's provider id might be `"bedrock"` vs `"amazon-bedrock"`,
   and the model id may need a prefix. *Unit-verify against pi-ai's registry before trusting.*
2. **Bearer wiring — env-direct vs `getApiKey`.** pi-ai references `AWS_BEARER_TOKEN_BEDROCK` directly (3×), so
   it may read the bearer from env itself rather than via `ModelBroker.getApiKey` (how anthropic/openrouter
   flow). Confirm the bearer actually reaches the request; if pi-ai self-serves it, `getApiKey` is moot for
   bedrock (document that asymmetry).
3. **REGION must match the spine (proven gotcha).** The bearer token is region-scoped: a **us-east-1 token
   403s against ap-south-1** (tested 2026-07-07). pi-ai's bedrock provider must target **`ap-south-1`** (the
   spine + `bedrockLlm.ts` region) with the **APAC** profile, and the provisioned `AWS_BEARER_TOKEN_BEDROCK`
   must be **ap-south-1-scoped**. Confirm pi-ai lets you set `AWS_REGION`/region for the bedrock provider.
4. **Nova format = Converse, not anthropic-messages.** pi-ai has `converse` (90×) + `nova` refs, so it should
   format `amazon.*` via the Converse API (works for Nova). Confirm it doesn't force the anthropic-messages
   invoke shape (Claude-on-Bedrock only) — that would break Nova. If it does, fall back to P2.
5. **Loud, DISTINCT invoke errors** (the lesson of this whole thread). Wrap resolution/invoke failures so
   `403 auth-invalid`, `model-not-invoke-granted`, and `region-mismatch` surface as *named* errors — not a
   generic "model resolution failed." The next such issue must be diagnosable, not mysterious.

## Fallback path (P2) — direct `bedrockGenerate` (only if P1's Nova-format check fails)
If pi-ai's bedrock provider turns out Nova-incompatible (delta #4), port `bedrockLlm.ts` directly into a
`Generate = (system,user)=>Promise<string>` (`src/seat/bedrockGenerate.ts`) — a bearer-token `fetch` to the
same endpoint, wired into the seam's Generate seam. This covers the **conversational path** (classify + reply,
which only need text→text) — enough for the first live turn (conversational, `approvals:"deny"`). The TASK
path (pi Agent) would still need P1. Keep P2 documented as the contained fallback, not the default.

## Fail-closed / least-privilege posture (carried, not re-derived)
- Reads `AWS_BEARER_TOKEN_BEDROCK` from env; **refuses at construction if blank** (inherited from
  `resolveLiveModel`). No fallback to another provider/path on a missing bedrock token.
- **Model id parameterized** (`NRT_MODEL` overrides `DEFAULT_MODEL.bedrock`) — if Claude-on-Bedrock ever
  un-gates, it's a config change, not a rewrite.

## Depends on (operator / box — NOT this code)
1. **Provision the wrapper task:** `AWS_BEARER_TOKEN_BEDROCK` **(ap-south-1-scoped)** as a secret + SG/subnet
   reach to the `bedrock-runtime` VPC endpoint. (The deployed Convex's working ap-south-1 token is the source
   of truth / shareable reference.)
2. **Box-verify:** with the ap-south-1 token, `registryGetModel("bedrock", "apac.amazon.nova-lite-v1:0")`
   resolves AND a real generate returns cleanly in-VPC. Doubles as confirming the Convex extraction path
   (the quarantine fix) is live.

## Honest state
Built against a **proven mechanism** (pi-ai bedrock+bearer+Nova support + `bedrockLlm.ts` in-VPC verification).
NOT yet proven: pi-ai's exact registry form (delta #1/#2), Nova-via-pi-ai (#4), and the region-matched token +
in-VPC reach (deps). Those are a unit-check (registry form) + a box-verify (in-VPC generate) — small, bounded,
against a target that demonstrably works. This is the code half; the provisioning + box-verify stay ML's.
