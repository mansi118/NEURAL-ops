---
neop_id: cortex
version: 1
role_family: meta
model: { planner: stub, executor: stub, verifier: stub }
limits: { max_replans: 1 }
memory: { read: true, write: true }
twin: { read: true }
tools: [ground_tool]
acp: { publishes: [cortex_answer] }
---
# Cortex NEop
First memory-aware NEop. Retrieves the seat's relevant memory in `assemble`, grounds
its answer in the retrieved chunks (a tool call), and writes a provenance-stamped
memory back on `run_end` (which also fires the STM→LTM consolidate hook). Exercises
the full read → use → write path through the MemoryBroker, fully offline in unit mode
(recorded bundles in `fixtures/memory/`). The backend (MemPalace = façade over Convex)
lives entirely behind the broker; this NEop never names it.
