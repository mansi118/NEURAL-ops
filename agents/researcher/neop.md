---
neop_id: researcher
version: 1
role_family: research
model: { planner: stub, executor: stub, verifier: stub }
limits: { max_replans: 2 }
memory: { read: true, write: false }
twin: { read: true }
tools: [researcher_tool]
acp: { publishes: [account_research] }
---
# Researcher NEop
Scaffolded NEop — replace this prose, the subagent prompts, and the fixtures with real content.
