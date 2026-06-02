"""nc-orchestrator — classify -> (neop, confidence), COC-1..5, resolve, dispatch, stream.

Calls the EXISTING `dispatch()` unchanged and threads (tenant, seat) from the envelope
into the dispatch msg. This module is the ONLY front-door file that imports dispatch —
to CALL it, never to change it. The latency boundary (overhead_ms) excludes dispatch
(Pi-agent work, NFR-1).
"""
from __future__ import annotations
import json, time
from runtime.core import dispatch
from frontdoor import gateway, loader

CONF_GATE = 0.7  # COC-2/3


def recorded_classifier(table):
    """Unit classifier seam: text substring -> (neop, confidence). Live model is integration."""
    def fn(text):
        for needle, val in table.items():
            if needle in text:
                return val[0], val[1]
        return ("echo", 0.5)
    return fn


def _direct_mention(envelope):
    for m in envelope.get("mentions", []):
        actor = m.get("actor", "")
        if actor.startswith("@"):
            return actor[1:]
    for tok in envelope["text"].split():
        if tok.startswith("@"):
            return tok[1:].strip(".,!?;:")
    return None


def route(envelope, classifier):
    """COC-1..5 routing decision."""
    direct = _direct_mention(envelope)
    if direct:                                          # COC-4: direct mention bypasses classify
        return {"action": "dispatch", "neop": direct, "confidence": 1.0, "reason": "COC-4 direct mention"}
    neop, conf = classifier(envelope["text"])           # COC-1
    if conf < CONF_GATE:                                # COC-2/3
        return {"action": "disambiguate", "confidence": conf,
                "question": "I'm not sure which agent you need — can you clarify?"}
    if "+" in neop:                                     # COC-5: multi-NEop chain guard
        if not envelope.get("metadata", {}).get("explicit_intent"):
            return {"action": "refuse", "reason": "COC-5 chain requires explicit intent", "neop": neop}
    return {"action": "dispatch", "neop": neop, "confidence": conf}


def _unit_backing(folder):
    """Load a NEop's recorded backing (first cassette/memory/twin + mocks) for unit dispatch."""
    fx = folder / "fixtures"

    def first(d):
        if d.exists():
            for p in sorted(d.glob("*.json")):
                return json.loads(p.read_text())
        return None

    cas = first(fx / "cassettes") or {}
    mocks_p = fx / "mocks" / "tools.json"
    mocks = json.loads(mocks_p.read_text()) if mocks_p.exists() else {}
    return cas, mocks, first(fx / "memory"), first(fx / "twin")


def stream_tokens(result):
    out = result.get("outputs") or {}
    last = list(out.values())[-1] if out else {}
    text = last.get("text") if isinstance(last, dict) else last
    text = text if text is not None else result.get("state", "")
    for tok in str(text).split(" "):
        yield tok


def handle(raw, classifier, *, mode="unit", rate=None, now_s=0.0,
           builtin_root="agents", tenant_root=None, operator_root=None):
    """Full round-trip: gateway-validate -> route -> resolve -> dispatch -> stream."""
    t0 = time.time()
    gateway.authenticate(raw)
    envelope = gateway.normalize(raw)
    tenant, seat = gateway.resolve_identity(envelope)
    (rate or gateway.RateLimiter()).check(tenant, seat, now_s)
    decision = route(envelope, classifier)
    if decision["action"] != "dispatch":
        return {"type": decision["action"], "tenant": tenant, "seat": seat,
                "decision": decision, "overhead_ms": round((time.time() - t0) * 1000)}
    folder = loader.resolve(decision["neop"], tenant, builtin_root=builtin_root,
                            tenant_root=tenant_root, operator_root=operator_root)
    if folder is None:
        return {"type": "error", "reason": f"neop '{decision['neop']}' not found",
                "tenant": tenant, "seat": seat, "overhead_ms": round((time.time() - t0) * 1000)}
    # THREAD identity into the dispatch msg, unchanged. dispatch()/core.py untouched.
    msg = {"text": envelope["text"], "tenant": tenant, "seat": seat}
    overhead_ms = round((time.time() - t0) * 1000)  # boundary: everything BEFORE dispatch (NFR-1)
    cas, mocks, mem, twin = _unit_backing(folder)
    result = dispatch(folder, msg, mode, cas, mocks, [], memory=mem, twin=twin)
    return {"type": "response", "neop": decision["neop"], "tenant": tenant, "seat": seat,
            "dispatched_msg": msg, "state": result["state"],
            "stream": list(stream_tokens(result)), "result": result, "overhead_ms": overhead_ms}
