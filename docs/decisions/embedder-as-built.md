# Decision — V1 embedder as-built: Bedrock Titan @1024 (Gemini-768 parked)

**Status: DECIDED 2026-06-29 · SHIPPED (NEURAL-ops #41 + Mempalace #25, merged).**
Supersedes the spec intent (NE-TSD-NC-V2 **S2 §2.5.3** = Gemini `embedding-001` @768) for V1, as an
explicit as-built deviation — not a silent drift.

## What shipped
- Live embedder = **Bedrock Titan Text Embeddings v2 @ 1024-dim**, reached **in-VPC over the
  `bedrock-runtime` PrivateLink endpoint** (no internet / no NAT). `Mempalace_NEOS/convex/lib/embedder.ts`
  selector → `qwen.js` (active); `gemini.js` parked. Schema `by_embedding` vector index = **1024**.
- **Auth:** a Bedrock bearer token (a service-specific credential, `aws iam create-service-specific-credential
  --service-name bedrock.amazonaws.com`, id `ACCARBD352VOQICTMHECZ`), stored in the Convex env. The
  embedding compute is **server-side in Convex** — never a runtime-container secret (D1/T1.5).

## The done-bar that was actually met (ranking, not "calls succeed")
`tools/embedder_proof.py` + `infra/build/embedder-verify.sh` assert **real ranked retrieval**: seed
distinct documents, query a *related* one, require a non-empty chunk with a real score and the related doc
ranking top. An empty-but-graceful result is **FAILURE** here (the opposite of the deployed-stack smoke,
whose graceful-empty tolerance is exactly why it did *not* catch a dead embedder). **Passed 2026-06-28** on
the live AWS stack. ⇒ "embedder live" here means *ranked hits*, per the correct done-bar.

## The Bedrock-access nuance (why this doesn't contradict "Bedrock blocked")
"Bedrock blocked" was diagnosed (2026-06-07) for the **LLM invoke path** (ValidationException
"Operation not allowed"). The **Titan-embeddings invoke path succeeded** (2026-06-28) — i.e. model access
is effectively available for Titan via the bearer-token path. The two Bedrock invoke paths have **diverged**;
do not carry "Bedrock blocked" as a blanket account fact. (The LLM went OpenRouter per D2 regardless, so the
LLM-side block is moot for shipping.)

## Why Titan over the spec's Gemini-768 (the reasons weighed)
| Reason to switch to Gemini-768 | Bites? |
|---|---|
| **Spec alignment** (S2 §2.5.3) | Recorded here as an as-built deviation instead — cheaper than re-platforming a working embedder. |
| **Portability / lock-in** | ⚠ Real but accepted for V1: Titan ties V1 to *this account's* Bedrock model-access state + the service-specific credential. Mitigation: the selector is one line; Gemini/Voyage are drop-in when warranted. |
| **Cost** | Not evaluated as decisive for the dogfood scale; revisit at fleet scale (AC-cost). |
None bite hard enough to switch a *working, ranking-proven* embedder before onboarding.

## Parked alternative + promotion trigger
- **Gemini `embedding-001` MRL-768** (PR #26, held open): the V1-canonical-by-spec embedder. Blocked from
  the live spine by **C2 — no NAT** (Gemini is external, no VPC endpoint). Also note **C1**: native-768 is
  unavailable on this key (only `gemini-embedding-001` @3072, 768 via MRL). See `confirmed-facts.md`.
- **Promote Gemini-768 only if** a reason above bites; it is **gated on the NAT decision** (an EIP for the
  spine). Promotion is a **free re-index pre-onboarding** (empty corpus) via the one-line selector flip —
  but a re-index is *not* free once a corpus exists, so decide before seats accrue memory.
- **Voyage** is the named long-term target (S2 forward-dep); a switch needs a key + a re-embed if its
  dimension/space differs from Titan's 1024.

## Owner / open items
- ML: confirm Titan-1024 is the intended V1 ship (portability accepted) **or** authorize NAT to promote
  Gemini-768. Either way this is now on record, not drifting.
- Reconcile NE-TSD-NC-V2 S2 §2.5.3 prose when the above is confirmed (annotated AS-BUILT for now).
