"""ACP signed envelopes — build / Ed25519 sign / verify, plus a deterministic keyring.

Offline-gradeable: keys derive from a seed (sha256(actor)) so signatures are stable in
tests; production keys rotate quarterly (deferred). No core import.
"""
from __future__ import annotations
import json, hashlib
from cryptography.hazmat.primitives.asymmetric import ed25519

INTENTS = {"delegate", "request_input", "redirect", "escalate", "inform", "refuse"}
MAX_HOPS = 5


def keyring(actors):
    """{actor: (private_key, public_key)} derived deterministically from the actor name."""
    ring = {}
    for a in actors:
        sk = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(a.encode()).digest())
        ring[a] = (sk, sk.public_key())
    return ring


def _canonical(env):
    body = {k: v for k, v in env.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _idem(conversation_id, to, capability, payload):
    return hashlib.sha256(
        json.dumps([conversation_id, to.get("actor"), capability, payload], sort_keys=True).encode()
    ).hexdigest()[:16]


def build(frm, to, intent, capability_required, payload, *,
          conversation_id, parent=None, hop_count=0, scope=None, ts="1970-01-01T00:00:00Z"):
    # ts + envelope_id are SEEDED (not wall-clock/random) so the Ed25519 signature and
    # idempotency_key are stable across runs — the ACP analog of cassette hash-stability.
    assert intent in INTENTS, f"bad intent {intent}"
    return {
        "acp_version": "1.0",
        "envelope_id": f"env_{conversation_id}_{hop_count}_{to.get('actor')}_{intent}",
        "conversation_id": conversation_id, "ts": ts,
        "from": frm, "to": to, "intent": intent,
        "capability_required": capability_required, "scope": scope or [],
        "payload": payload, "hop_count": hop_count, "max_hops": MAX_HOPS,
        "parent_envelope_id": parent,
        "idempotency_key": _idem(conversation_id, to, capability_required, payload),
    }


def sign(env, sk):
    env = dict(env)
    env["signature"] = "ed25519:" + sk.sign(_canonical(env)).hex()
    return env


def verify(env, pk):
    sig = env.get("signature", "")
    if not sig.startswith("ed25519:"):
        return False
    try:
        pk.verify(bytes.fromhex(sig.split(":", 1)[1]), _canonical(env))
        return True
    except Exception:
        return False
