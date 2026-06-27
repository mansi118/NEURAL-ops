# Embedder Unblock — Checklist (activation step 2, before governance/onboarding)

> **✅ RESOLVED 2026-06-28 — and the recommendation below got corrected by a live test.** This checklist
> recommended **Gemini**. But verifying the child (a live `bedrock invoke-model` with the account creds)
> overturned the stale "Bedrock blocked" assumption: **Bedrock Titan v2 embeddings ARE available**, and a
> `bedrock-runtime` **VPC endpoint** exists — so Convex reaches Bedrock with **no internet/NAT**, which is
> strictly better for the no-NAT spine than Gemini (Google's API has no VPC endpoint → would need NAT).
> **Shipped: Bedrock Titan via PrivateLink** (Mempalace `lib/embedder.ts` → `qwen.js`; Gemini parked).
> Auth = a Bedrock bearer token minted via `aws iam create-service-specific-credential --service-name
> bedrock.amazonaws.com`, stored in Secrets Manager, set in the Convex env (`convex env set
> AWS_BEARER_TOKEN_BEDROCK`). **PROVEN live: `tools/embedder_proof.py` 7-chunk ranked retrieval, top hit =
> the semantic target with zero lexical overlap, via `infra/build/embedder-verify.sh`.** The Gemini-specific
> steps below are retained as the parked-alternative path (valid if a NAT/EIP ever lands).


**Why first:** the spine smoke passes with the embedder deferred (`broker.retrieve` asserts *graceful*,
not *non-empty*). But a real seat hits **live semantic retrieval on day one** — blind retrieval is a bad
first impression you'd have to walk back. Unblock the embedder, confirm real hits, *then* governance + onboard.

## ⚠️ The trap (traced 2026-06-28 — it is NOT "swap the placeholder")
1. **Embeddings are computed SERVER-SIDE in Convex**, not in the runtime (skill invariant 8; `convex/lib/qwen.ts:24`
   says the credential "must live in the **CONVEX** environment"). ⇒ The `EMBEDDER_API_KEY` placeholder I set on
   the **runtime** ECS task does **nothing** for retrieval. Setting it there and expecting hits is the trap.
2. **The active embedder is Bedrock Titan v2** (`convex/lib/qwen.ts`: `EMBEDDER_PROVIDER="bedrock-titan-v2"`,
   model `amazon.titan-embed-text-v2:0`, reads `process.env.AWS_BEARER_TOKEN_BEDROCK`). **Bedrock is blocked
   account-wide** (CLAUDE.md) — and the spine ran `enable_bedrock=false`. So the wired path is **dead as-is**.
3. **No Gemini *embeddings* lib exists yet** — only a Gemini *LLM* lib (`convex/lib/geminiLlm.ts`, reads
   `GEMINI_API_KEY`). Prior embedders tried + abandoned (per `qwen.ts`): Qwen3 (HF credits depleted), Voyage
   (no key), Gemini (billing was off). The `.env` has `GEMINI_API_KEY` + `OPENROUTER_API_KEY` on hand.

## Decision (pick the provider first)
- **Recommended: Gemini embeddings** — key already on hand. Model `gemini-embedding-001` (or `text-embedding-004`),
  endpoint `…/v1beta/models/<model>:embedContent?key=$GEMINI_API_KEY`. Needs a small lib (mirror `geminiLlm.ts`).
- Voyage — the skill's stated "live target," but **no Voyage key on hand** (would need provisioning).
- Bedrock Titan — already wired, but **blocked**; only if Bedrock access is opened on the account.

## Steps (push-button once the provider is chosen)
- [ ] **1. Implement the provider** (if Gemini): add `convex/lib/geminiEmbed.ts` exporting `embedOne`,
      `embedBatchTexts`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `EMBEDDER_PROVIDER`, `embeddingConfigured()`
      — same surface `convex/lib/qwen.ts` exports today. Reads `GEMINI_API_KEY`.
- [ ] **2. Switch the wiring** from `qwen.js` → the new lib in `convex/ingestion/embed.ts` (and `ingest.ts`,
      which imports `EMBEDDING_MODEL`/`embedOne` from `../lib/qwen.js`). Keep the file name or update both imports.
- [ ] **3. Match dimensions to the vector index.** `convex/schema.ts` defines the `embeddings` vector index with a
      fixed `dimensions`. Gemini `gemini-embedding-001` = 3072 (configurable) / `text-embedding-004` = 768; Titan v2 = 1024.
      Set `EMBEDDING_DIMENSIONS` to match the index, or update the index (the table is versioned by `model` +
      `modelVersion`, so a new model tags new rows — old rows stay queryable under their own model).
- [ ] **4. Put `GEMINI_API_KEY` in the CONVEX environment** (NOT the runtime). Two options:
      - `npx convex env set GEMINI_API_KEY <val>` against the backend — run **in-VPC** (Convex is internal;
        reuse the `spine-verify.sh` CodeBuild pattern with `CONVEX_SELF_HOSTED_URL`+admin key). Survives restarts.
      - or add `GEMINI_API_KEY` as a secret + inject into the Convex ECS task def (`convex.tf` `secrets`). Heavier.
      The runtime `EMBEDDER_API_KEY`/`__DEFERRED__` placeholder can stay or be removed — it is not the live path.
- [ ] **5. `npx convex deploy`** the updated functions (in-VPC, via `spine-verify.sh`).
- [ ] **6. Re-embed if needed.** Fresh tenant has ~no vectors, so usually nothing to backfill; if any rows were
      written embedder-off, re-run the ingestion/embed action for them (or accept they index under no model).
- [ ] **7. Confirm REAL hits (not graceful-empty).** Write a known doc, semantic-search a paraphrase, assert a
      ranked non-empty chunk with a sane score. Extend `tools/deployed_stack_smoke.py` retrieve check from
      `"chunks" in r` to `len(r["chunks"]) > 0 with score`, or a one-off in-VPC check. THIS is the gate for step 2.
- [ ] **8. Check `embeddingHealth`** — `convex/http.ts:342` surfaces embedder health at session start; confirm green.

## Done = a live write is retrievable by meaning on the deployed stack. Then → governance flip (Policy v1) → onboard ≥5.
