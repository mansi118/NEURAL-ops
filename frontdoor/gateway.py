"""nc-gateway — normalize inbound to a NeuralChatMessage envelope, authenticate,
resolve (tenant, seat), rate-limit. Above dispatch(); imports no agent-loop code.
Offline-gradeable: in-memory rate-limit, clock injected (no wall-clock dependency).
"""
from __future__ import annotations

REQUIRED_RAW = ("channel", "user_id", "text")


class GatewayError(RuntimeError):
    pass


class AuthError(GatewayError):
    pass


class RateLimited(GatewayError):
    def __init__(self, scope):
        super().__init__(f"429 rate limited: {scope}")
        self.http = 429


def authenticate(raw):
    """V1: Matrix token + HMAC-signed adapter call. Offline = presence check (CA-4)."""
    if not raw.get("token"):
        raise AuthError("missing auth token")
    if not raw.get("hmac"):
        raise AuthError("missing adapter HMAC")


def normalize(raw, *, msg_id="msg_unit", ts="1970-01-01T00:00:00Z"):
    """Adapter payload -> canonical NeuralChatMessage envelope (S2 §2.2)."""
    for k in REQUIRED_RAW:
        if k not in raw:
            raise GatewayError(f"raw missing required field '{k}'")
    uid = raw["user_id"]
    tenant = uid.split(":", 1)[0] if ":" in uid else raw.get("tenant_id")
    return {
        "msg_id": raw.get("msg_id", msg_id),
        "tenant_id": tenant,
        "channel": raw["channel"],
        "conversation_id": raw.get("conversation_id"),
        "thread_id": raw.get("thread_id"),
        "user_id": uid,
        "text": raw["text"],
        "attachments": raw.get("attachments", []),
        "mentions": raw.get("mentions", []),
        "ts": raw.get("ts", ts),
        "metadata": raw.get("metadata", {}),
    }


def resolve_identity(envelope):
    """Resolve (tenant, requester) from user_id = "tenant:requester".

    requester is the HUMAN making the request — used for rate-limit + attribution.
    It is NOT the run seat: the run seat is the routed NEop's id (set by the
    orchestrator), which keys that NEop's own memory and twin. Conflating the two
    cross-wires memory/twin — so this returns the requester, never a run seat.
    """
    uid = envelope["user_id"]
    if ":" not in uid:
        raise GatewayError(f"user_id '{uid}' not in tenant:requester form")
    tenant, requester = uid.split(":", 1)
    if envelope.get("tenant_id") and envelope["tenant_id"] != tenant:
        raise GatewayError("tenant_id does not match user_id prefix")
    return tenant, requester


class RateLimiter:
    """GW-3: 60 msg/min/seat, 16 concurrent Pi-agent runs/tenant -> 429."""
    PER_SEAT_PER_MIN = 60
    PER_TENANT_CONCURRENT = 16

    def __init__(self):
        self._minute = {}      # (tenant, seat, minute) -> count
        self._concurrent = {}  # tenant -> active runs

    def check(self, tenant, seat, now_s):
        minute = int(now_s // 60)
        key = (tenant, seat, minute)
        self._minute[key] = self._minute.get(key, 0) + 1
        if self._minute[key] > self.PER_SEAT_PER_MIN:
            raise RateLimited(f"{seat} > {self.PER_SEAT_PER_MIN}/min")
        if self._concurrent.get(tenant, 0) >= self.PER_TENANT_CONCURRENT:
            raise RateLimited(f"{tenant} concurrent >= {self.PER_TENANT_CONCURRENT}")

    def enter(self, tenant):
        self._concurrent[tenant] = self._concurrent.get(tenant, 0) + 1

    def leave(self, tenant):
        self._concurrent[tenant] = max(0, self._concurrent.get(tenant, 0) - 1)
