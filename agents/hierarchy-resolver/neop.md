---
neop_id: hierarchy-resolver
version: 1
role_family: meta
pattern: workflow         # deterministic org-chart resolution (delegate down / escalate up), not autonomous (G1)
model: { planner: stub, executor: stub, verifier: stub }
limits: { max_replans: 1 }
memory: { read: true, write: false }
twin: { read: true }
tools: [resolve_hierarchy]
acp: { publishes: [hierarchy-resolver] }
---
# Hierarchy Resolver NEop

The meta-NEop that answers ACP routing's org-chart questions: route a capability DOWN to the nearest
subordinate that holds it (delegation), or route a blocked/over-scope action UP the reporting line
(escalation). A **workflow** — deterministic resolution over a validated org-chart, no autonomy.

Logic lives in `acp/hierarchy.py` (`delegate`/`escalate`/`escalation_chain`/`subordinates`, pure +
tested in `tests/test_hierarchy.py`). The live `resolve_hierarchy` tool binds to those resolvers; the
fixture mock mirrors the exact output. A capability with no capable subordinate returns
`delegate_to: null` (the caller escalates instead). The ACP Router consumes this resolver.
