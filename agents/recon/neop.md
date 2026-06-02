---
neop_id: recon
version: 1
role_family: sales
model: { planner: stub, executor: stub, verifier: stub }
limits: { max_replans: 2, phase_timeout_s: { plan: 10, execute: 20, verify: 10 } }
tools: [search_leads, enrich_lead, dedupe]
acp: { publishes: [recon_leads] }
---
# Recon NEop
First real-work NEop (role_family=sales -> full plan -> execute -> verify). Builds a
deduplicated lead list via a 3-task DAG:

    find_leads (search_leads) -> enrich (enrich_lead) -> dedupe (dedupe)

with `depends_on` edges. Each task's output threads into the next task's input
scope. Proves the runtime's DAG executor and edge-aware golden plans under `nrt`,
fully offline (no gateway, memory, twin, or ACP).
