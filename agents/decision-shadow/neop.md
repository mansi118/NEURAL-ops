---
neop_id: decision-shadow
version: 1
role_family: reactive
pattern: workflow         # predefined reactive compare (twin vs actual), no replan loop
model: { executor: stub, verifier: stub }
limits: { max_replans: 0 }
memory: { read: true, write: false }
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

**Twin keying (docs/decisions/twin-keying.md):** the Shadow predicts **the user**, whose twin is keyed by
`requester`. It is user-*about*, not user-*less* — its dispatch (incl. background triggers) MUST thread the
target user as `requester`, or `twin_owner = requester or seat` falls back to this NEop's own twin and the
Shadow would predict against the wrong model. The `or seat` fallback is for genuinely user-less runs only.
