---
neop_id: echo
version: 1
role_family: meta
model:
  planner: stub
  executor: stub
  verifier: stub
limits:
  max_replans: 2
  phase_timeout_s: { plan: 10, execute: 10, verify: 10 }
tools: [echo_tool]
acp:
  publishes: [echo]
---
# Echo NEop
The hello-world Pi-agent. Proves the runtime contract: load -> plan -> execute -> verify -> DONE.
It echoes the user's input text back, unchanged.
