# ADR-llm — Runtime LLM stack (D2 / M0·T0.1) — ✅ DECIDED + SHIPPED (M2)

**Status:** DECIDED + **SHIPPED in M2 (NEURAL-ops #46, merged 2026-06-29)** — **OpenRouter primary**
(**by decision**: no Anthropic key on hand; OpenRouter is the on-hand path. NOT because Bedrock is blocked —
Bedrock generative works in-VPC, see below). ML may override with a
direct Anthropic key (then `llm_provider=anthropic`). **Model id as shipped:** classifier =
**`anthropic/claude-haiku-4.5`** via OpenRouter. NOTE: the earlier `anthropic/claude-3.5-haiku` slug
**404s on the gateway** ("no endpoints found") — corrected during M2's live COC re-grade (4/4 agreement).
Wired: `ecs.tf` `CLASSIFIER_PROVIDER=var.llm_provider` (default `openrouter`); `OPENROUTER_API_KEY` is a
managed Secrets Manager slot (`variables.tf`) — set the value out-of-band before the runtime classifies.
Gate ⛔G-a; sets which key the runtime boots with (`CLASSIFIER_PROVIDER` → `ANTHROPIC_API_KEY` vs
`OPENROUTER_API_KEY`) and drives AC-10 cost. **Still open:** plan/general model ids + AC-10 cost (record below).

**Bedrock scope — CORRECTED 2026-06-29 (T0):** "Bedrock blocked" is **FALSE**, including for generative.
The original 2026-06-07 ValidationException was an **Anthropic-model** use-case-form block, not an account
or service block. Verified in-VPC: **Titan embeddings** LIVE (ranked-retrieval, 2026-06-28) AND **Nova
generative** LIVE (`apac.amazon.nova-lite-v1:0`, serving ingestion extraction, 2026-06-29) — both via the
bedrock-runtime PrivateLink endpoint + bearer token. The **only** Bedrock block is **Anthropic models**
(model-specific). Do **NOT** carry "Bedrock blocked" — blanket or LLM-scoped — as a fact. OpenRouter is the
runtime LLM **by decision**, not by Bedrock constraint.

**Spec deviation (as-built):** NE-TSD-NC-V2 §3.5.1 (`docs/NE-TSD-NC-V2-S3-Runtime-Ops.md:324`) records the
*intended* Sonnet/GPT-5.4-mini/Haiku stack (GLM = V2 fallback); the as-built V1 ships OpenRouter-routed.
That spec line is annotated AS-BUILT; reconcile fully when plan/general ids are picked.

## The contradiction (D2)
- **NE-TSD-NC-V2 §3.5.1:** planning = **Claude Sonnet** · general = **GPT-5.4-mini** · classifier = **Haiku-class**; **GLM-5 is a V2 *local fallback*** (not the primary).
- **Recent build direction:** "GLM-5.2 via OpenRouter **replacing** Anthropic." Replacement ≠ fallback.

## What's true in the code/account (traced)
- Runtime selects provider via `CLASSIFIER_PROVIDER` (`runtime/selfcheck.py`): `anthropic`→`ANTHROPIC_API_KEY`, `openrouter`→`OPENROUTER_API_KEY`, default `anthropic`. Boot requires the primary key.
- **On hand:** `OPENROUTER_API_KEY` (in `.env`, also a Secrets Manager slot can be added). **No Anthropic key** is on hand. Bedrock generative works in-VPC (Nova/Llama), but **Anthropic-via-Bedrock is out** (use-case form pending) — so Bedrock is not a path to Anthropic models specifically.
- The **live NEop execution path is the jcode adapter** (config_render already supports an `anthropic-api` provider AND an `openrouter` provider — built). So either choice is wireable.
- ⇒ Practically, with no Anthropic key on hand, **OpenRouter is the ready path** unless ML provides a direct Anthropic/OpenAI key. (This is a key-availability call, not a Bedrock-block call.)

## Options for ML
1. **OpenRouter as primary (replacement)** — use the on-hand key; pick model ids (e.g. GLM-5.2, or `anthropic/claude-…` via OpenRouter). Cheapest to ship; matches recent direction. Spec §3.5.1 doc must be updated to record the replacement.
2. **Spec-canonical (Sonnet/GPT-5.4-mini/Haiku) with GLM as fallback** — requires ML to supply the Anthropic + OpenAI keys (not on hand). More cost, matches the written spec.

## Decision
> _ML to record here: chosen stack, model ids per role (plan/general/classifier), and primary vs fallback.
> Then: set the corresponding Secrets Manager secret(s), set `CLASSIFIER_PROVIDER`, and update the stale
> doc (§3.5.1 / the neos-implementation skill). Wired in M2._

**Until decided, M2 (LLM wiring) is blocked; M1 (embedder) and M0·T0.3 proceed independently.**
