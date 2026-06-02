---
neop_id: decision-shadow
version: 1
role_family: reactive
model: { executor: stub, verifier: stub }
limits: { max_replans: 0 }
twin: { read: true }
shadow: true
tools: [predict_tool]
acp: { publishes: [shadow] }
---
# Decision Shadow NEop
Flow 5. On an observable decision, predicts what the seat's twin would do and records
predicted-vs-actual. role_family=reactive -> phases [execute, verify] (no upfront plan).
The twin is prepended in `assemble`; the prediction is compared to the actual action and
emitted as a `shadow_prediction` event **after the terminal state is set**, so it is
structurally off the critical path (non-blocking, Flow 5). The fidelity clock that
consumes these signals is P-later.
