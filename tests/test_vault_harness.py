"""Vault harness tests — one pass over candidate writes (promote/hold/reject), the durable emit sink,
redaction carried through, cross-pass do-not-re-promote, and rollback clearing the marker for re-promote.
Timestamps injected; pure. Run: python3 tests/test_vault_harness.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.vault_harness import run_vault_pass, VaultPromoter, InMemoryPromotedStore  # noqa: E402

T0 = "2026-06-01T00:00:00Z"


def _rec(key="e1", cat="fact", conf=0.9, content="hello", approval="promote"):
    return {"category": cat, "confidence": conf, "content": content, "approval": approval,
            "dedup_key": key,
            "provenance": {"source_adapter": "matrix", "source_external_id": key,
                           "author_type": "user", "author_id": "u1"}}


def test_promote_hold_reject_in_one_pass():
    emitted = []
    recs = [
        _rec("ok", conf=0.9),                                   # promote
        _rec("low", conf=0.1),                                  # VL-1 hold (below floor)
        {**_rec("noprov"), "provenance": {}},                  # VL-3 reject (no provenance)
        _rec("needsrev", approval=None),                       # VL-4 hold (no approval)
    ]
    r = run_vault_pass(recs, emit=emitted.append, now_ts=T0)
    s = r["summary"]
    assert s == {"candidates": 4, "promoted": 1, "held": 2, "rejected": 1, "redacted": 0}, s
    assert [e["dedup_key"] for e in emitted] == ["ok"], emitted
    assert emitted[0]["rollback_armed"] is True and emitted[0]["promoted_at"] == T0
    print("PASS test_promote_hold_reject_in_one_pass")


def test_redaction_carried_into_promoted_record():
    r = run_vault_pass([_rec("pii", content="mail me at a@b.com")], now_ts=T0)
    rec = r["promoted"][0]["record"]
    assert "[REDACTED:email]" in rec["content"] and rec["pii_redacted"] == ["email"], rec
    assert r["summary"]["redacted"] == 1
    print("PASS test_redaction_carried_into_promoted_record")


def test_cross_pass_do_not_re_promote():
    emitted = []
    recs = [_rec("dur", conf=0.9)]
    p = VaultPromoter(lambda: recs, emit=emitted.append, now_ts=T0)
    r1 = p.tick()
    r2 = p.tick()                                              # next nightly tick, same candidate
    assert r1["summary"]["promoted"] == 1 and r2["summary"]["promoted"] == 0, (r1["summary"], r2["summary"])
    assert r2["decisions"][0]["decision"] == "reject" and "do_not_re_promote" in r2["decisions"][0]["reason"]
    assert len(emitted) == 1 and "dur" in p.promoted, (emitted, p.promoted.all())
    print("PASS test_cross_pass_do_not_re_promote")


def test_rollback_clears_marker_and_allows_repromote():
    emitted = []
    recs = [_rec("fix", conf=0.9)]
    p = VaultPromoter(lambda: recs, emit=emitted.append, now_ts=T0)
    promoted_rec = p.tick()["promoted"][0]["record"]          # arm the promotion
    # roll it back a week later (within the 30d TTL) -> marker cleared
    rb = p.rollback(promoted_rec, now_ts="2026-06-08T00:00:00Z")
    assert rb["decision"] == "rollback" and "fix" not in p.promoted, (rb, p.promoted.all())
    # now the corrected record can promote again on the next tick
    r3 = p.tick()
    assert r3["summary"]["promoted"] == 1, r3["summary"]
    print("PASS test_rollback_clears_marker_and_allows_repromote")


def test_rollback_refuses_outside_ttl():
    p = VaultPromoter(lambda: [], now_ts=T0)
    promoted_rec = run_vault_pass([_rec("old", conf=0.9)], now_ts=T0)["promoted"][0]["record"]
    late = p.rollback(promoted_rec, now_ts="2026-08-01T00:00:00Z")   # ~60d later, past 30d TTL
    assert late["decision"] == "reject" and "window lapsed" in late["reason"], late
    print("PASS test_rollback_refuses_outside_ttl")


def test_emit_error_never_fails_pass():
    def boom(_):
        raise RuntimeError("palace sink down")
    r = run_vault_pass([_rec("ok", conf=0.9)], emit=boom, now_ts=T0)
    assert r["summary"]["promoted"] == 1, r["summary"]
    print("PASS test_emit_error_never_fails_pass")


def test_approvals_seam_callable():
    recs = [_rec("k", approval=None)]                          # no inline approval
    p = VaultPromoter(lambda: recs, approvals=lambda: {"k": "promote"}, now_ts=T0)   # Decision-Queue verdict
    assert p.tick()["summary"]["promoted"] == 1
    print("PASS test_approvals_seam_callable")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL VAULT HARNESS TESTS PASS")
