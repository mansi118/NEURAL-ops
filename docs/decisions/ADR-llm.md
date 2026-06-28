# ADR-llm — Runtime LLM stack (D2 / M0·T0.1) — ⛔ DECISION PENDING (ML)

**Status:** OPEN — needs ML. This is gate ⛔G-a: it sets which Secrets Manager key the runtime boots with
(`CLASSIFIER_PROVIDER` → `ANTHROPIC_API_KEY` vs `OPENROUTER_API_KEY`) and drives AC-10 cost.

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
