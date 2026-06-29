"""nc-channels AS service-layer tests — the offline-verifiable wire policy.

Covers hs_token auth (header + legacy query fallback), transaction dedup (at-least-once delivery),
the inbound transaction → raws mapping (loop filter applied), the outbound CS-API send descriptor,
and puppet-namespace enforcement. The live HTTP server + CS-API call are box-gated (raise) and not run.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from nc_channels import matrix_adapter as ma
from nc_channels.service import ASRegistration, ASService
from frontdoor import orchestrator


def make_reg(**over):
    base = dict(
        id="neop-bridge", url="https://neop-as.internal:8009", tenant="neuraledge",
        sender_localpart="neop", user_namespace_regex=r"@neop_.*:server",
        as_token="AS_TOK", hs_token="HS_TOK", adapter_hmac_key="HMAC_KEY", server_name="server")
    base.update(over)
    return ASRegistration(**base)


def make_service():
    classifier = orchestrator.recorded_classifier({"echo": ("echo", 0.95)})
    return ASService(make_reg(), handle=orchestrator.handle, classifier=classifier)


def msg_event(body="echo please", sender="@alice:server", event_id="$e1"):
    return {"type": "m.room.message", "event_id": event_id, "room_id": "!r:server",
            "sender": sender, "origin_server_ts": 1_700_000_000_000,
            "content": {"msgtype": "m.text", "body": body}}


# ---- registration / construction guards ----

def test_service_requires_tenant():
    with pytest.raises(ValueError):
        ASService(make_reg(tenant=""), handle=orchestrator.handle, classifier=None)


def test_service_requires_hs_token():
    with pytest.raises(ValueError):
        ASService(make_reg(hs_token=""), handle=orchestrator.handle, classifier=None)


# ---- inbound auth ----

def test_verify_hs_token():
    svc = make_service()
    assert svc.verify_hs_token("HS_TOK") is True
    assert svc.verify_hs_token("wrong") is False
    assert svc.verify_hs_token(None) is False


def test_bearer_from_headers_prefers_authorization():
    assert ASService.bearer_from_headers({"Authorization": "Bearer abc"}) == "abc"
    assert ASService.bearer_from_headers({"authorization": "Bearer xyz"}) == "xyz"


def test_bearer_legacy_query_fallback():
    assert ASService.bearer_from_headers({}, {"access_token": "legacy"}) == "legacy"
    assert ASService.bearer_from_headers({}) is None


# ---- transaction processing + dedup ----

def test_process_transaction_maps_routable_events():
    svc = make_service()
    res = svc.process_transaction("txn1", {"events": [msg_event()]})
    assert len(res.processed) == 1
    raw = res.processed[0]
    assert raw["channel"] == "matrix" and raw["user_id"] == "neuraledge:alice"
    assert ma.verify_adapter_hmac(raw, "HMAC_KEY") is True


def test_process_transaction_skips_own_echo():
    svc = make_service()
    res = svc.process_transaction("txn1", {"events": [msg_event(sender="@neop:server")]})
    assert res.processed == [] and res.skipped == 1


def test_transaction_dedup_is_idempotent():
    svc = make_service()
    first = svc.process_transaction("txnA", {"events": [msg_event()]})
    second = svc.process_transaction("txnA", {"events": [msg_event()]})
    assert len(first.processed) == 1
    assert second.deduped is True and second.processed == []


def test_mixed_transaction_counts_skips():
    svc = make_service()
    res = svc.process_transaction("txnM", {"events": [
        msg_event(event_id="$h", sender="@bob:server"),
        msg_event(event_id="$x", sender="@neop:server"),   # our echo -> skip
        {"type": "m.room.member", "event_id": "$m", "sender": "@c:server", "content": {}},  # not a msg -> skip
    ]})
    assert len(res.processed) == 1 and res.skipped == 2


# ---- outbound send descriptor ----

def test_reply_send_builds_cs_api_descriptor():
    svc = make_service()
    result = {"stream": ["hello", "world"]}
    send = svc.reply_send("!r:server", result, "out1")
    assert send.method == "PUT"
    assert send.path == "/_matrix/client/v3/rooms/!r:server/send/m.room.message/out1"
    assert send.body == {"msgtype": "m.text", "body": "hello world"}
    assert send.query == {}


def test_reply_send_puppet_within_namespace():
    svc = make_service()
    send = svc.reply_send("!r:server", {"stream": ["hi"]}, "out2", puppet_localpart="neop_planner")
    assert send.query == {"user_id": "@neop_planner:server"}


def test_reply_send_puppet_outside_namespace_rejected():
    svc = make_service()
    with pytest.raises(ValueError):
        svc.reply_send("!r:server", {"stream": ["hi"]}, "out3", puppet_localpart="eve")


# ---- box-gated boundary ----

def test_live_wire_is_box_gated():
    svc = make_service()
    with pytest.raises(NotImplementedError):
        svc.serve("0.0.0.0", 8009)


# ---- end-to-end: transaction → handle → reply_send (offline, unit dispatch) ----

def test_transaction_to_reply_round_trip(tmp_path):
    neop = tmp_path / "echo"
    (neop / "fixtures" / "cassettes").mkdir(parents=True)
    (neop / "neop.md").write_text("# echo\n")
    (neop / "fixtures" / "cassettes" / "c.json").write_text('{"turns": []}')

    svc = make_service()
    res = svc.process_transaction("txnE", {"events": [msg_event()]})
    assert len(res.processed) == 1
    raw = res.processed[0]
    result = orchestrator.handle(raw, svc._classifier, mode="unit", builtin_root=str(tmp_path))
    assert result["type"] == "response" and result["seat"] == "echo"
    send = svc.reply_send(raw["conversation_id"], result, "outE")
    assert send.path.endswith("/outE")
    assert send.body["msgtype"] == "m.text"
