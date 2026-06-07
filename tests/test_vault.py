"""Vault promotion (Flow 4) tests — VL-1..VL-5 + conservative-bias write path.

Vault is a layer over the broker's candidate writes; core.py is untouched.
Run: python3 tests/test_vault.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.vault import promote, promote_all, redact, rollback   # noqa: E402
from runtime.core import MemoryBroker                     # noqa: E402


def _rec(**kw):
    base = {"content": "NeuralEDGE signed the Zoo Media retainer", "category": "decision",
            "confidence": 0.8,
            "provenance": {"source_adapter": "mcp", "source_external_id": "k1",
                           "author_type": "neop", "author_id": "cortex"}}
    base.update(kw)
    return base


def test_vl1_confidence_floor():
    d = promote(_rec(confidence=0.2))                     # below 'decision' floor (0.6)
    assert d["decision"] == "hold" and "VL-1" in d["reason"], d
    print("PASS test_vl1_confidence_floor")


def test_vl2_redaction():
    d = promote(_rec(content="reach me at ml@neuraledge.ai key AKIAABCDEFGHIJKLMNOP", approval="promote"))
    assert d["decision"] == "promote", d
    assert "ml@neuraledge.ai" not in d["record"]["content"] and "AKIA" not in d["record"]["content"], d
    assert {"email", "aws_key"} <= set(d["record"]["pii_redacted"]), d
    print("PASS test_vl2_redaction")


def test_vl3_provenance_required():
    r = _rec(approval="promote"); r["provenance"] = {"source_adapter": "mcp"}   # missing fields
    d = promote(r)
    assert d["decision"] == "reject" and "VL-3" in d["reason"], d
    print("PASS test_vl3_provenance_required")


def test_vl4_conservative_and_consent():
    assert promote(_rec())["gates"]["VL-4"] == "needs_review"          # no approval -> hold
    assert promote(_rec())["decision"] == "hold"
    assert promote(_rec(approval="reject"))["decision"] == "reject"    # explicit reject
    assert promote(_rec(approval="promote"))["decision"] == "promote"  # explicit consent
    print("PASS test_vl4_conservative_and_consent")


def test_vl5_rollback_and_no_repromote():
    d = promote(_rec(approval="promote"))
    rec = d["record"]
    assert rec["rollback_armed"] is True and rec["do_not_re_promote"] is True and rec["rollback_ttl_days"] == 30, d
    again = promote(_rec(approval="promote"), promoted_keys={d["key"]})
    assert again["decision"] == "reject" and "VL-5" in again["reason"], again
    print("PASS test_vl5_rollback_and_no_repromote")


def test_vl5_rollback_reverses_within_ttl():
    # the OTHER half of VL-5: an armed promotion can actually be reversed (was armed-but-inert).
    p = promote(_rec(approval="promote"), now_ts="2026-01-01T00:00:00Z")["record"]
    r = rollback(p, now_ts="2026-01-20T00:00:00Z")                 # 19d < 30d TTL
    assert r["decision"] == "rollback" and r["tombstone"]["key"] == "k1", r
    assert r["clear_do_not_re_promote"] is True, r
    print("PASS test_vl5_rollback_reverses_within_ttl")


def test_vl5_rollback_refuses():
    # never promoted -> nothing to roll back
    nope = rollback(_rec())
    assert nope["decision"] == "reject" and "nothing to roll back" in nope["reason"], nope
    # past the 30-day window -> refuse
    p = promote(_rec(approval="promote"), now_ts="2026-01-01T00:00:00Z")["record"]
    late = rollback(p, now_ts="2026-03-15T00:00:00Z")             # ~73d > 30d
    assert late["decision"] == "reject" and "lapsed" in late["reason"], late
    print("PASS test_vl5_rollback_refuses")


def test_vl5_rollback_then_repromote():
    # round-trip: promote -> blocked by do-not-re-promote -> rollback clears it -> re-promote OK
    p = promote(_rec(approval="promote"))
    keys = {p["key"]}
    assert promote(_rec(approval="promote"), promoted_keys=keys)["decision"] == "reject"   # VL-5 block
    r = rollback(p["record"], now_ts="2026-01-10T00:00:00Z")
    if r["clear_do_not_re_promote"]:
        keys.discard(r["key"])                                    # caller drops the retracted key
    assert promote(_rec(approval="promote"), promoted_keys=keys)["decision"] == "promote", keys
    print("PASS test_vl5_rollback_then_repromote")


def test_broker_writes_dont_auto_promote():
    # THE POINT: a raw NEop run-summary write must NOT auto-promote -> no palace pollution.
    b = MemoryBroker("unit", [], bundle={"chunks": [{"id": "c1", "tenant": "neuraledge", "text": "x"}], "provenance": []})
    b.write("neuraledge", "cortex", {"content": "[cortex] DONE", "cites": ["c1"], "category": "run"})
    decisions = promote_all(b.writes)
    assert decisions and decisions[0]["decision"] == "hold", decisions   # no confidence/approval -> held
    # ...but an explicit, confident, approved record clears all five gates
    ok = promote(_rec(approval="promote"))
    assert ok["decision"] == "promote" and list(ok["gates"]) == ["VL-1", "VL-2", "VL-3", "VL-4", "VL-5"], ok
    print("PASS test_broker_writes_dont_auto_promote")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL VAULT TESTS PASS")
