"""ACP router (nc-acp) — verify a signed envelope (ACP-1..4), route to dispatch(B).

Beside the runtime; calls dispatch() unchanged. B runs under ITS own scope (to.actor),
with the sender carried as requester for audit. parent_envelope_id links the chain.
"""
from __future__ import annotations
import json, pathlib
from runtime.core import dispatch
from frontdoor import loader
from acp import envelope as E


def _happy_backing(folder):
    """Recorded backing for a NEop, preferring a cassette whose verify passes (DONE path)."""
    fx = pathlib.Path(folder) / "fixtures"

    def first(d):
        if d.exists():
            for p in sorted(d.glob("*.json")):
                return json.loads(p.read_text())
        return None

    cas, cdir = {}, fx / "cassettes"
    if cdir.exists():
        cands = sorted(cdir.glob("*.json"))
        for p in cands:
            c = json.loads(p.read_text())
            vk = [k for k in c if k.startswith("verify:")]
            if not vk or all((c[k] or {}).get("pass") for k in vk):
                cas = c
                break
        else:
            cas = json.loads(cands[0].read_text()) if cands else {}
    mp = fx / "mocks" / "tools.json"
    mocks = json.loads(mp.read_text()) if mp.exists() else {}
    return cas, mocks, first(fx / "memory"), first(fx / "twin")


class Router:
    """Stateless ACP router. registry: capability->neop_id; ring: actor->(sk,pk)."""

    def __init__(self, registry, ring, *, agents_root="agents", backing=_happy_backing, audit=None):
        self.registry = registry
        self.ring = ring
        self.agents_root = agents_root
        self.backing = backing
        self.audit = audit if audit is not None else []

    def route(self, env, *, visited=None):
        visited = visited or set()
        self.audit.append({"envelope_id": env.get("envelope_id"), "intent": env.get("intent"),
                           "from": env.get("from", {}).get("actor"), "to": env.get("to", {}).get("actor"),
                           "parent": env.get("parent_envelope_id")})
        sender = env.get("from", {}).get("actor")
        kp = self.ring.get(sender)
        if not kp or not E.verify(env, kp[1]):                       # ACP-1 signature
            return self._refuse(env, "ACP-1 signature invalid")
        if env.get("intent") not in E.INTENTS or "capability_required" not in env:  # ACP-1 schema
            return self._refuse(env, "ACP-1 schema invalid")
        if env.get("hop_count", 0) > env.get("max_hops", E.MAX_HOPS):  # ACP-3 hops
            return self._refuse(env, "ACP-3 max_hops exceeded")
        cap = env["capability_required"]
        target = self.registry.get(cap)
        if not target:                                                # ACP-4 capability match
            return self._refuse(env, f"ACP-4 no publisher for capability '{cap}'")
        if target in visited:                                         # ACP-2 cycle
            return self._refuse(env, f"ACP-2 cycle: '{target}' already in chain")
        tenant = env["to"]["tenant"]
        folder = loader.resolve(target, tenant, builtin_root=self.agents_root)
        if folder is None:
            return self._refuse(env, f"target neop '{target}' not found")
        # route -> dispatch(B). B runs under its own seat; sender = requester (audit).
        msg = {"text": env["payload"].get("text", ""), "tenant": tenant, "seat": target, "requester": sender}
        cas, mocks, mem, twin = self.backing(folder)
        result = dispatch(folder, msg, "unit", cas, mocks, [], memory=mem, twin=twin)
        inform = E.build(frm={"tenant": tenant, "actor": target, "type": "neop"}, to=env["from"],
                         intent="inform", capability_required=cap,
                         payload={"state": result["state"], "outputs": result["outputs"], "neop": target},
                         conversation_id=env["conversation_id"], parent=env["envelope_id"],
                         hop_count=env.get("hop_count", 0) + 1)
        return E.sign(inform, self.ring[target][0])

    def _refuse(self, env, reason):
        to = env.get("to", {})
        r = E.build(frm=to, to=env.get("from", {}), intent="refuse",
                    capability_required=env.get("capability_required", ""), payload={"reason": reason},
                    conversation_id=env.get("conversation_id", "?"), parent=env.get("envelope_id"),
                    hop_count=env.get("hop_count", 0) + 1)
        actor = to.get("actor")
        return E.sign(r, self.ring[actor][0]) if actor in self.ring else r
