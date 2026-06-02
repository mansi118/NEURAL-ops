---
neop_id: proposal-writer
version: 1
role_family: meta
model: { planner: stub, executor: stub, verifier: stub }
limits: { max_replans: 2 }
memory: { read: true, write: false }
twin: { read: true }
tools: [proposal-writer_tool]
acp: { publishes: [proposal_draft] }
---
# Proposal-writer NEop
Scaffolded NEop — replace this prose, the subagent prompts, and the fixtures with real content.
