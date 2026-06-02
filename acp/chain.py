"""Orchestrator-driven chain runner (COC-5 gated).

The coordinator owns the chain: one signed `delegate` envelope per capability hop,
each NEop's outputs threaded into the next hop's payload; cycle + hop_count enforced by
the router. Audit reconstructs via parent_envelope_id. Sequential (DAG is deferred).
"""
from __future__ import annotations
from acp import envelope as E


def run_chain(capabilities, initial_text, router, ring, *, tenant="neuraledge",
              coordinator="coordinator", explicit_intent=False, conversation_id="conv1"):
    if len(capabilities) > 1 and not explicit_intent:          # COC-5
        return {"status": "refused", "reason": "COC-5 chain requires explicit intent", "hops": []}
    coord = {"tenant": tenant, "actor": coordinator, "type": "coordinator"}
    visited, hops, resp = set(), [], None
    payload, parent = {"text": initial_text}, None
    for i, cap in enumerate(capabilities):
        target = router.registry.get(cap)
        to = {"tenant": tenant, "actor": target or "?", "type": "neop"}
        env = E.sign(E.build(coord, to, "delegate", cap, payload,
                             conversation_id=conversation_id, parent=parent, hop_count=i),
                     ring[coordinator][0])
        resp = router.route(env, visited=visited)
        hops.append({"capability": cap, "to": target, "intent": resp["intent"]})
        if resp["intent"] == "refuse":
            return {"status": "refused", "reason": resp["payload"]["reason"],
                    "hops": hops, "audit": router.audit}
        visited.add(target)
        payload = {"text": initial_text, "upstream": resp["payload"]["outputs"]}
        parent = resp["envelope_id"]
    return {"status": "done", "hops": hops, "final": resp["payload"] if resp else None,
            "audit": router.audit}
