---
neop_id: ping
version: 1
role_family: executor
model: { executor: stub }
limits: { max_replans: 0 }
tools: [ping_tool]
acp: { publishes: [ping] }
---
# Ping NEop
Pure executor. role_family=executor -> phase set is [EXECUTE] only.
No planner model call, no verify tax. Proves phases are a function of role_family.
