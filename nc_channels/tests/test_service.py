"""nc-channels AS service-layer tests — the offline-verifiable wire policy.

Covers hs_token auth (header + legacy query fallback), transaction dedup (at-least-once delivery),
the inbound transaction → raws mapping (loop filter applied), the outbound CS-API send descriptor,
and puppet-namespace enforcement. The live HTTP server + CS-API call are box-gated (raise) and not run.
"""
import json
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


# ---- the live wire: request CONSTRUCTION unit-tested via injected transport ----
# The live Synapse handshake itself stays box-proven (never mocked, D1); what we CAN prove offline is
# that _cs_api_call assembles the exact CS-API request the spec requires. serve() is no longer gated —
# it's implemented (Bar 1a hardcoded reflect); the live round-trip is proven on the box, not here.

def test_cs_api_call_builds_request():
    captured = {}

    def capture(method, url, data, headers):
        captured.update(method=method, url=url, data=data, headers=headers)
        return 200, {"event_id": "$sent"}

    svc = ASService(make_reg(), handle=orchestrator.handle, classifier=None,
                    hs_base_url="http://localhost:8008/", transport=capture)
    send = svc.reply_send("!r:server", {"stream": ["hi", "there"]}, "out1")
    status, resp = svc._cs_api_call(send)

    assert captured["method"] == "PUT"
    assert captured["url"] == (
        "http://localhost:8008/_matrix/client/v3/rooms/!r:server/send/m.room.message/out1")
    assert captured["headers"]["Authorization"] == "Bearer AS_TOK"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert json.loads(captured["data"].decode("utf-8")) == {"msgtype": "m.text", "body": "hi there"}
    assert status == 200 and resp == {"event_id": "$sent"}


def test_cs_api_call_encodes_puppet_query():
    captured = {}

    def capture(method, url, data, headers):
        captured.update(url=url)
        return 200, {}

    svc = ASService(make_reg(), handle=orchestrator.handle, classifier=None, transport=capture)
    send = svc.reply_send("!r:server", {"stream": ["hi"]}, "out2", puppet_localpart="neop_planner")
    svc._cs_api_call(send)
    # puppet mxid rides as the ?user_id= query param (AS acting-as a namespaced NEop)
    assert captured["url"].endswith("/send/m.room.message/out2?user_id=%40neop_planner%3Aserver")


# ---- B-fwd: the reflect=False forward to the Hermes seat wrapper (step 3) ----
# Construction unit-tested via injected transport; the live Hermes hop is box-proven (never mocked).

def _raw(text="what's my project?"):
    return {"text": text, "conversation_id": "!r:server", "user_id": "neuraledge:alice", "msg_id": "$e1"}


def test_seat_forward_builds_request():
    captured = {}

    def capture(method, url, data, headers):
        captured.update(method=method, url=url, data=data, headers=headers)
        return 200, {"kind": "reply", "text": "Your project is BLUEFERN."}

    svc = ASService(make_reg(), handle=orchestrator.handle, classifier=None,
                    seat_url="http://hermes:8090/seat/turn/", forward_token="FWD_TOK", transport=capture)
    env = svc._seat_forward(_raw())

    assert captured["method"] == "POST"
    assert captured["url"] == "http://hermes:8090/seat/turn"           # trailing "/" normalized
    assert captured["headers"]["Authorization"] == "Bearer FWD_TOK"    # bridge presents the shared secret
    # message + Matrix identity only — NO scope keys (the wrapper bakes palaceId/neopId from its own env):
    body = json.loads(captured["data"].decode("utf-8"))
    assert body == {"message": "what's my project?", "conversationId": "!r:server",
                    "userId": "neuraledge:alice", "idempotencyKey": "$e1"}
    assert not ({"palaceId", "neopId", "tool", "params", "scope"} & set(body))
    assert env["text"] == "Your project is BLUEFERN."


def test_seat_forward_fails_closed_without_token():
    svc = ASService(make_reg(), handle=orchestrator.handle, classifier=None,
                    seat_url="http://hermes:8090/seat/turn", forward_token="")  # blank token
    with pytest.raises(RuntimeError, match="forward_token"):
        svc._seat_forward(_raw())


def test_seat_forward_fails_closed_without_url():
    svc = ASService(make_reg(), handle=orchestrator.handle, classifier=None, forward_token="FWD_TOK")
    with pytest.raises(RuntimeError, match="seat_url"):
        svc._seat_forward(_raw())


def test_seat_forward_raises_on_non_200():
    def capture(method, url, data, headers):
        return 403, {"errcode": "M_FORBIDDEN"}

    svc = ASService(make_reg(), handle=orchestrator.handle, classifier=None,
                    seat_url="http://hermes:8090/seat/turn", forward_token="FWD_TOK", transport=capture)
    with pytest.raises(RuntimeError, match="seat forward failed: http 403"):
        svc._seat_forward(_raw())


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


# ---- Decision-Queue verdict routing (fidelity signal) ----

def verdict_event(proposal_id="p1", verdict="approve", seat="aria", by="@mansi:server"):
    return {"type": "m.neop.verdict", "event_id": "$v1", "room_id": "!dq:server",
            "sender": "@alice:server",
            "content": {"proposal_id": proposal_id, "verdict": verdict, "seat": seat, "by": by}}


def test_process_transaction_routes_verdict_to_injected_sink():
    captured = []
    svc = ASService(make_reg(), handle=orchestrator.handle,
                    classifier=orchestrator.recorded_classifier({"echo": ("echo", 0.95)}),
                    on_verdict=lambda tenant, v: captured.append((tenant, v)))
    res = svc.process_transaction("txnV", {"events": [verdict_event()]})
    assert res.processed == [] and len(res.verdicts) == 1
    # the sink gets the tenant + the parsed verdict (seat carried so it keys the right twin)
    assert captured == [("neuraledge",
                         {"proposal_id": "p1", "verdict": "approve", "seat": "aria", "by": "@mansi:server"})]


def test_verdict_without_sink_is_detected_not_persisted():
    svc = make_service()   # no on_verdict → the bridge has no palace access; detected + counted only
    res = svc.process_transaction("txnV2", {"events": [verdict_event(verdict="reject")]})
    assert len(res.verdicts) == 1 and res.verdicts[0]["verdict"] == "reject"


def test_message_and_verdict_in_one_transaction():
    captured = []
    svc = ASService(make_reg(), handle=orchestrator.handle,
                    classifier=orchestrator.recorded_classifier({"echo": ("echo", 0.95)}),
                    on_verdict=lambda t, v: captured.append(v))
    res = svc.process_transaction("txnMix", {"events": [msg_event(), verdict_event()]})
    assert len(res.processed) == 1 and len(res.verdicts) == 1 and len(captured) == 1
