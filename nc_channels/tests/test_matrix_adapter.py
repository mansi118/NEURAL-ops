"""nc-channels pure-core tests — the Matrix adapter bound to the REAL front-door seam.

These assert two things: (1) the mapping/identity/hmac/render functions are correct in isolation, and
(2) a mapped `raw` actually satisfies the first-party gateway contract — authenticate/normalize/
resolve_identity accept it and resolve the identity we intend. No network; the AS HTTP service +
CS-API send + Synapse deploy are box-gated (service.py / nc-channels-trace.md), not exercised here.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from nc_channels import matrix_adapter as ma
from frontdoor import gateway, orchestrator


TENANT = "neuraledge"
TOKEN = "as_token_xyz"
HMAC_KEY = "adapter-secret-key"


def make_event(**over):
    ev = {
        "type": "m.room.message",
        "event_id": "$evt1",
        "room_id": "!room:server",
        "sender": "@alice:server",
        "origin_server_ts": 1_700_000_000_000,
        "content": {"msgtype": "m.text", "body": "hello twin"},
    }
    ev.update(over)
    return ev


# ---- identity_from_mxid ----

def test_identity_maps_to_tenant_requester():
    assert ma.identity_from_mxid("@alice:server", TENANT) == "neuraledge:alice"


def test_identity_blank_tenant_fails_closed():
    with pytest.raises(ma.AdapterError):
        ma.identity_from_mxid("@alice:server", "")


@pytest.mark.parametrize("bad", ["", "alice:server", "@:server", "@alice", "@alicenoserver"])
def test_identity_malformed_mxid_fails_closed(bad):
    with pytest.raises(ma.AdapterError):
        ma.identity_from_mxid(bad, TENANT)


# ---- HMAC (CA-4) ----

def test_hmac_is_deterministic_and_keyed():
    a = ma.mint_adapter_hmac(channel="matrix", user_id="t:u", text="hi", ts="T", key="k1")
    b = ma.mint_adapter_hmac(channel="matrix", user_id="t:u", text="hi", ts="T", key="k1")
    c = ma.mint_adapter_hmac(channel="matrix", user_id="t:u", text="hi", ts="T", key="k2")
    assert a == b and a != c


def test_hmac_blank_key_fails_closed():
    with pytest.raises(ma.AdapterError):
        ma.mint_adapter_hmac(channel="matrix", user_id="t:u", text="hi", ts="T", key="")


def test_verify_hmac_roundtrip_and_tamper():
    raw = ma.matrix_message_to_raw(make_event(), tenant=TENANT, token=TOKEN, hmac_key=HMAC_KEY)
    assert ma.verify_adapter_hmac(raw, HMAC_KEY) is True
    raw["text"] = "tampered"
    assert ma.verify_adapter_hmac(raw, HMAC_KEY) is False


# ---- is_routable_message (loop/echo filter) ----

def test_routable_human_text_message():
    assert ma.is_routable_message(make_event()) is True


def test_skip_non_message_event():
    assert ma.is_routable_message(make_event(type="m.room.member")) is False


def test_skip_non_text_msgtype():
    ev = make_event(content={"msgtype": "m.image", "body": "x", "url": "mxc://.."})
    assert ma.is_routable_message(ev) is False


def test_skip_edit_relation_on_ingest():
    ev = make_event(content={"msgtype": "m.text", "body": "* edit",
                             "m.relates_to": {"rel_type": "m.replace", "event_id": "$old"}})
    assert ma.is_routable_message(ev) is False


def test_skip_our_own_as_puppet_echo():
    ev = make_event(sender="@neop_echo:server")
    assert ma.is_routable_message(ev, as_localparts=["neop_echo", "neop_planner"]) is False
    # a real human in the same room is still routable
    assert ma.is_routable_message(make_event(), as_localparts=["neop_echo"]) is True


# ---- matrix_message_to_raw → gateway contract ----

def test_raw_has_required_gateway_fields():
    raw = ma.matrix_message_to_raw(make_event(), tenant=TENANT, token=TOKEN, hmac_key=HMAC_KEY)
    for k in gateway.REQUIRED_RAW:
        assert k in raw
    assert raw["channel"] == "matrix"
    assert raw["user_id"] == "neuraledge:alice"
    assert raw["text"] == "hello twin"
    assert raw["conversation_id"] == "!room:server"


def test_raw_passes_gateway_authenticate():
    raw = ma.matrix_message_to_raw(make_event(), tenant=TENANT, token=TOKEN, hmac_key=HMAC_KEY)
    gateway.authenticate(raw)  # must not raise (token + hmac present, CA-4)


def test_raw_normalizes_and_resolves_to_intended_identity():
    raw = ma.matrix_message_to_raw(make_event(), tenant=TENANT, token=TOKEN, hmac_key=HMAC_KEY)
    env = gateway.normalize(raw)
    tenant, requester = gateway.resolve_identity(env)
    assert (tenant, requester) == ("neuraledge", "alice")
    assert env["channel"] == "matrix"
    assert env["conversation_id"] == "!room:server"


def test_mentions_mapped_for_coc4_direct_mention():
    ev = make_event(content={"msgtype": "m.text", "body": "do it",
                             "m.mentions": {"user_ids": ["@neop_planner:server"]}})
    raw = ma.matrix_message_to_raw(ev, tenant=TENANT, token=TOKEN, hmac_key=HMAC_KEY)
    assert raw["mentions"] == [{"actor": "@neop_planner:server"}]


def test_ts_iso_from_origin_server_ts():
    raw = ma.matrix_message_to_raw(make_event(), tenant=TENANT, token=TOKEN, hmac_key=HMAC_KEY)
    assert raw["ts"] == "2023-11-14T22:13:20Z"


# ---- end-to-end through the real handle() seam (mocked classifier+dispatch via unit cassette) ----

def test_event_round_trips_through_orchestrator_handle(tmp_path):
    """Matrix event → raw → orchestrator.handle (unit mode) → stream → Matrix outbound content.
    Uses a minimal recorded NEop folder so dispatch runs offline (no model, no network)."""
    # minimal unit NEop "echo" with a cassette so dispatch is deterministic
    neop = tmp_path / "echo"
    (neop / "fixtures" / "cassettes").mkdir(parents=True)
    (neop / "neop.md").write_text("# echo\n")
    (neop / "fixtures" / "cassettes" / "c.json").write_text('{"turns": []}')

    ev = make_event(content={"msgtype": "m.text", "body": "echo please"})
    raw = ma.matrix_message_to_raw(ev, tenant=TENANT, token=TOKEN, hmac_key=HMAC_KEY)
    classifier = orchestrator.recorded_classifier({"echo": ("echo", 0.95)})
    result = orchestrator.handle(raw, classifier, mode="unit", builtin_root=str(tmp_path))

    assert result["type"] == "response"
    assert result["tenant"] == "neuraledge" and result["requester"] == "alice"
    assert result["seat"] == "echo"
    body = ma.stream_to_text(result)
    content = ma.outbound_message(body)
    assert content["msgtype"] == "m.text"
    assert isinstance(content["body"], str)


# ---- outbound builders ----

def test_outbound_message_shape():
    assert ma.outbound_message("hi") == {"msgtype": "m.text", "body": "hi"}


def test_outbound_edit_shape():
    e = ma.outbound_edit("new text", "$orig")
    assert e["m.relates_to"] == {"rel_type": "m.replace", "event_id": "$orig"}
    assert e["m.new_content"] == {"msgtype": "m.text", "body": "new text"}
    assert e["body"] == "* new text"


def test_stream_to_text_rejoins_on_space():
    assert ma.stream_to_text({"stream": ["hello", "there", "world"]}) == "hello there world"
    assert ma.stream_to_text({}) == ""


# ---- Decision-Queue verdict parsing (fidelity signal source) ----

def test_verdict_from_event_valid():
    ev = {"type": "m.neop.verdict",
          "content": {"proposal_id": "p1", "verdict": "approve", "seat": "aria", "by": "@ml:s"}}
    assert ma.verdict_from_event(ev) == {"proposal_id": "p1", "verdict": "approve", "seat": "aria", "by": "@ml:s"}


@pytest.mark.parametrize("content", [
    {"verdict": "approve"},                       # no seat → can't key the signal
    {"verdict": "approve", "seat": "   "},         # blank seat
    {"verdict": "maybe", "seat": "aria"},          # not approve/reject
    {"seat": "aria"},                              # no verdict
])
def test_verdict_from_event_rejects_unusable(content):
    assert ma.verdict_from_event({"type": "m.neop.verdict", "content": content}) is None


def test_verdict_from_event_ignores_non_verdict_types():
    assert ma.verdict_from_event({"type": "m.room.message", "content": {"verdict": "approve", "seat": "aria"}}) is None
    assert ma.verdict_from_event({}) is None
