---
neop_id: acp-router
version: 1
role_family: meta
pattern: workflow         # routing = classify capability -> dispatch to publisher (ACP-1..4 gates), pre-wired (G1)
model: { planner: stub, executor: stub, verifier: stub }
limits: { max_replans: 1 }
memory: { read: true, write: false }
twin: { read: true }
tools: [route_envelope]
acp: { publishes: [acp-router] }
---
# ACP Router NEop (Flow 7)

Formalizes the existing ACP router-seam as a meta-NEop: verify a signed envelope, gate it
(ACP-1 signature · ACP-2 no cycle · ACP-3 max_hops · ACP-4 capability has a publisher), dispatch to
the publishing NEop, and return its signed `inform` response. A **workflow** (routing pattern:
classify → dispatch), not autonomy — the decomposition is the publisher's, not the router's.

Logic lives in `acp/router.py` (`Router.route`, with `acp/envelope.py` signing + `acp/capabilities.py`
registry). The live `route_envelope` tool binds to `Router.route`; the fixture mock mirrors a real
routed `inform` envelope (a delegate to `echo` → its DONE response; signature stable via seeded ts).
A refused envelope returns a signed `refuse` carrying the gate reason.
