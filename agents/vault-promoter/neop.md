---
neop_id: vault-promoter
version: 1
role_family: meta
pattern: workflow         # pre-wired 5-gate pipeline (VL-1..VL-5), deterministic — NOT dynamic autonomy (G1)
model: { planner: stub, executor: stub, verifier: stub }
limits: { max_replans: 1 }
memory: { read: true, write: true }   # reads LTM candidates; writes the promoted (durable) record
twin: { read: true }
tools: [vault_promote]
acp: { publishes: [vault-promoter] }
---
# Vault Promoter NEop (Flow 4)

The meta-NEop that decides which candidate memory writes become **durable** (LTM → Vault). It is a
**workflow**, not an autonomous agent: the decomposition is fixed — gather candidate records, run the
five conservative gates over each, promote only those that clear all five. The autonomy is nil; the
gates are the whole policy.

The decision logic lives in `runtime/vault.py` (`promote` / `promote_all`, pure + deterministic,
already unit-tested in `tests/test_vault.py`). This NEop is the **dispatch-contract wrapper**: it runs
that logic on the proven plan→execute→verify loop so promotion is an auditable NEop run, not an ad-hoc
script. The live `vault_promote` tool binds to `runtime.vault.promote(record, approvals=…)`; in unit
mode the fixture mock mirrors its exact output.

The five gates (in order; conservative — a raw write does NOT auto-promote):
- **VL-1** per-category confidence floor.
- **VL-2** PII / secret redaction (masked, not a reject).
- **VL-3** provenance present (`source_adapter`, `source_external_id`, `author_*`).
- **VL-4** approval via the Decision Queue (conservative bias → `needs_review`).
- **VL-5** rollback armed (30-day reversible) + do-not-re-promote marker.

Outcomes per candidate: `promote` | `hold` (low-confidence / needs-review) | `reject`. Only `promote`
writes through the broker to the Vault tier; `hold`/`reject` stay as candidates with the gate reason
recorded for audit. The async cadence (nightly / session-close) is a scheduling concern, not this NEop.
