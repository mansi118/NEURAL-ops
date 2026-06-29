# ADR-llm — Runtime LLM stack (D2 / M0·T0.1) — ✅ DECIDED + SHIPPED (M2)

**Status:** DECIDED + **SHIPPED in M2 (NEURAL-ops #46, merged 2026-06-29)** — **OpenRouter primary**
(FORCED: no Anthropic key on hand + Bedrock LLM-invoke blocked; only ready path). ML may override with a
direct Anthropic key (then `llm_provider=anthropic`). **Model id as shipped:** classifier =
**`anthropic/claude-haiku-4.5`** via OpenRouter. NOTE: the earlier `anthropic/claude-3.5-haiku` slug
**404s on the gateway** ("no endpoints found") — corrected during M2's live COC re-grade (4/4 agreement).
Wired: `ecs.tf` `CLASSIFIER_PROVIDER=var.llm_provider` (default `openrouter`); `OPENROUTER_API_KEY` is a
managed Secrets Manager slot (`variables.tf`) — set the value out-of-band before the runtime classifies.
Gate ⛔G-a; sets which key the runtime boots with (`CLASSIFIER_PROVIDER` → `ANTHROPIC_API_KEY` vs
`OPENROUTER_API_KEY`) and drives AC-10 cost. **Still open:** plan/general model ids + AC-10 cost (record below).

**Bedrock scope (was over-broad):** "Bedrock blocked" is true for the **LLM invoke path** (2026-06-07
ValidationException). It is **NOT** true for **Titan embeddings**, which are LIVE in-VPC via the
bedrock-runtime PrivateLink endpoint (ranked-retrieval proven 2026-06-28) — see `embedder-as-built.md`.
The two Bedrock invoke paths have diverged; don't carry "Bedrock blocked" as a blanket fact.

**Spec deviation (as-built):** NE-TSD-NC-V2 §3.5.1 (`docs/NE-TSD-NC-V2-S3-Runtime-Ops.md:324`) records the
*intended* Sonnet/GPT-5.4-mini/Haiku stack (GLM = V2 fallback); the as-built V1 ships OpenRouter-routed.
That spec line is annotated AS-BUILT; reconcile fully when plan/general ids are picked.

## The contradiction (D2)
- **NE-TSD-NC-V2 §3.5.1:** planning = **Claude Sonnet** · general = **GPT-5.4-mini** · classifier = **Haiku-class**; **GLM-5 is a V2 *local fallback*** (not the primary).
- **Recent build direction:** "GLM-5.2 via OpenRouter **replacing** Anthropic." Replacement ≠ fallback.

## What's true in the code/account (traced)
- Runtime selects provider via `CLASSIFIER_PROVIDER` (`runtime/selfcheck.py`): `anthropic`→`ANTHROPIC_API_KEY`, `openrouter`→`OPENROUTER_API_KEY`, default `anthropic`. Boot requires the primary key.
- **On hand:** `OPENROUTER_API_KEY` (in `.env`, also a Secrets Manager slot can be added). **No Anthropic key** is on hand. **Bedrock is blocked** account-wide (so Anthropic-via-Bedrock is out).
- The **live NEop execution path is the jcode adapter** (config_render already supports an `anthropic-api` provider AND an `openrouter` provider — built). So either choice is wireable.
- ⇒ Practically, with no Anthropic key + Bedrock blocked, **OpenRouter is the only ready path** unless ML provides a direct Anthropic/OpenAI key.

## Options for ML
1. **OpenRouter as primary (replacement)** — use the on-hand key; pick model ids (e.g. GLM-5.2, or `anthropic/claude-…` via OpenRouter). Cheapest to ship; matches recent direction. Spec §3.5.1 doc must be updated to record the replacement.
2. **Spec-canonical (Sonnet/GPT-5.4-mini/Haiku) with GLM as fallback** — requires ML to supply the Anthropic + OpenAI keys (not on hand). More cost, matches the written spec.

## Decision
> _ML to record here: chosen stack, model ids per role (plan/general/classifier), and primary vs fallback.
> Then: set the corresponding Secrets Manager secret(s), set `CLASSIFIER_PROVIDER`, and update the stale
> doc (§3.5.1 / the neos-implementation skill). Wired in M2._

**Until decided, M2 (LLM wiring) is blocked; M1 (embedder) and M0·T0.3 proceed independently.**
