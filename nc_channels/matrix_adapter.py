"""Matrix Application-Service transport adapter — the PURE core (offline-testable, no network).

Binds to the existing front door: an inbound Synapse AS transaction (an `m.room.message` event) is
mapped to the gateway's `raw`, then handed to `frontdoor.orchestrator.handle(raw, classifier, ...)`;
the returned `result["stream"]` is rendered back to a Matrix room message.

What's HERE (pure, tested): mxid→`tenant:requester` mapping · the CA-4 adapter HMAC · event→`raw`
mapping · the loop/echo filter · stream→text render · the outbound message/edit content builders.
What's BOX-GATED (the live AS HTTP service: the `/transactions` ingest endpoint + the CS-API send, and
the Synapse deploy + public ingress) lives in `service.py` behind the same kind of gate the jcode
adapter puts on `_docker_run`. Contract refs + risks: docs/deployment/nc-channels-trace.md.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
from datetime import datetime, timezone
from typing import Iterable, Optional

CHANNEL = "matrix"


class AdapterError(RuntimeError):
    pass


def identity_from_mxid(mxid: str, tenant: str) -> str:
    """`@localpart:server` + the AS's tenant → the gateway's `user_id` = "tenant:requester".

    One AS per tenant (CA-5), so the tenant is the adapter instance's, never taken from the event.
    Fail-closed on a blank tenant or a malformed mxid."""
    if not (tenant and tenant.strip()):
        raise AdapterError("blank tenant — refusing (one AS per tenant, CA-5)")
    if not (mxid and mxid.startswith("@") and ":" in mxid):
        raise AdapterError(f"malformed mxid {mxid!r} (want @localpart:server)")
    localpart = mxid[1:].split(":", 1)[0]
    if not localpart:
        raise AdapterError(f"empty localpart in mxid {mxid!r}")
    return f"{tenant}:{localpart}"


def mint_adapter_hmac(*, channel: str, user_id: str, text: str, ts: str, key: str) -> str:
    """CA-4: each adapter→gateway call is HMAC-signed with the adapter's per-channel key. Deterministic
    HMAC-SHA256 hex over a canonical field tuple. The gateway checks presence today; this is the real
    signature for when Layer-2 verifies (mirrors the shim's forward-looking Ed25519)."""
    if not (key and key.strip()):
        raise AdapterError("blank adapter HMAC key — refusing (CA-4)")
    msg = json.dumps([channel, user_id, text, ts], separators=(",", ":"), ensure_ascii=False).encode()
    return _hmac.new(key.encode(), msg, hashlib.sha256).hexdigest()


def verify_adapter_hmac(raw: dict, key: str) -> bool:
    """Constant-time re-check of a raw's HMAC (the gateway side, for when L2 verification lands)."""
    expected = mint_adapter_hmac(channel=raw.get("channel", ""), user_id=raw.get("user_id", ""),
                                 text=raw.get("text", ""), ts=raw.get("ts", ""), key=key)
    return _hmac.compare_digest(expected, raw.get("hmac", ""))


def _iso_from_ms(ms: Optional[int]) -> str:
    """origin_server_ts (unix ms) → ISO-8601 UTC. Deterministic given the input; epoch 0 if absent."""
    try:
        return datetime.fromtimestamp((ms or 0) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError):
        return "1970-01-01T00:00:00Z"


def _mentions(content: dict) -> list:
    """Map Matrix `m.mentions.user_ids` → the envelope's `mentions` shape."""
    ids = ((content.get("m.mentions") or {}).get("user_ids")) or []
    return [{"actor": uid} for uid in ids if isinstance(uid, str)]


def is_routable_message(event: dict, *, as_localparts: Iterable[str] = ()) -> bool:
    """True only for a human text message we should route. Skips:
      - non `m.room.message` / non `m.text` events,
      - edits/relations on ingest (`m.relates_to`) — we don't re-route our own streamed edits,
      - the AS's own sends + NEop-puppet echoes (loop prevention — never re-ingest what we emitted)."""
    if event.get("type") != "m.room.message":
        return False
    content = event.get("content") or {}
    if content.get("msgtype") != "m.text":
        return False
    if "m.relates_to" in content:
        return False
    sender = event.get("sender") or ""
    local = sender[1:].split(":", 1)[0] if sender.startswith("@") else ""
    return local not in set(as_localparts)


VERDICT_TYPE = "m.neop.verdict"


def verdict_from_event(event: dict) -> Optional[dict]:
    """Parse an `m.neop.verdict` Decision-Queue event → {proposal_id, verdict, seat, by} or None.

    The other fidelity signal source (see fidelity-signal-generation): a human approve/reject on a NEop's
    output. Only `approve`/`reject` are valid, and the `seat` (the originating NEop the nc-web contract
    echoes via encodeVerdict) MUST be present — a verdict we can't key to a seat is not a fidelity signal,
    so we return None and the caller skips it. PURE: parse only; persistence is the caller's injected sink
    (the bridge itself has no palace access — it routes the verdict to an in-VPC sink)."""
    if not isinstance(event, dict) or event.get("type") != VERDICT_TYPE:
        return None
    content = event.get("content") or {}
    verdict = content.get("verdict")
    seat = content.get("seat")
    if verdict not in ("approve", "reject") or not (isinstance(seat, str) and seat.strip()):
        return None
    return {"proposal_id": content.get("proposal_id"), "verdict": verdict,
            "seat": seat, "by": content.get("by")}


def matrix_message_to_raw(event: dict, *, tenant: str, token: str, hmac_key: str) -> dict:
    """Map an `m.room.message` event → the gateway's `raw` (filter with is_routable_message first).

    Produces exactly the gateway contract: REQUIRED `channel`/`user_id`/`text` + `token`+`hmac` for
    authenticate (CA-4), and `conversation_id`=room_id so the reply targets the right room."""
    content = event.get("content") or {}
    text = content.get("body") or ""
    user_id = identity_from_mxid(event.get("sender", ""), tenant)
    ts = _iso_from_ms(event.get("origin_server_ts"))
    raw = {
        "channel": CHANNEL,
        "user_id": user_id,
        "text": text,
        "msg_id": event.get("event_id"),
        "conversation_id": event.get("room_id"),
        "thread_id": (content.get("m.relates_to") or {}).get("event_id"),
        "mentions": _mentions(content),
        "ts": ts,
        "token": token,
        "metadata": {"matrix_event_id": event.get("event_id"), "room_id": event.get("room_id")},
    }
    raw["hmac"] = mint_adapter_hmac(channel=CHANNEL, user_id=user_id, text=text, ts=ts, key=hmac_key)
    return raw


def stream_to_text(result: dict) -> str:
    """result['stream'] (the token list from orchestrator.handle) → the outbound Matrix body.
    The orchestrator's stream_tokens() space-splits the text, so rejoin on a space (NOT "") to
    reconstruct it. Send-on-complete (the robust default; incremental m.replace edits = RISK-1)."""
    return " ".join(result.get("stream") or [])


def outbound_message(body: str) -> dict:
    """CS-API `content` for a plain text send."""
    return {"msgtype": "m.text", "body": body}


def outbound_edit(new_body: str, original_event_id: str) -> dict:
    """CS-API `content` for an `m.replace` edit (incremental streaming — used sparingly per RISK-1).
    Carries the spec fallback `body` (for non-edit-aware clients) + `m.new_content` + the relation."""
    return {
        "msgtype": "m.text",
        "body": "* " + new_body,
        "m.new_content": {"msgtype": "m.text", "body": new_body},
        "m.relates_to": {"rel_type": "m.replace", "event_id": original_event_id},
    }
