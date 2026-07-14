"""Vault runner — the driver + live-seam wiring, offline (injected make / fake _post; no network).
Proves a passing candidate promotes end to end through VaultPromoter, approvals fold from human verdicts,
and the palace promoted-store is inert at construction. Run: python3 tests/test_vault_runner.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime import vault_runner as vr   # noqa: E402
from runtime.vault_harness import VaultPromoter, InMemoryPromotedStore  # noqa: E402
from runtime import memory as m   # noqa: E402

# a candidate that clears VL-1 (confidence) + VL-3 (provenance); key = source_external_id.
CAND = {"content": "we chose vendor A", "category": "fact", "confidence": 0.9,
        "provenance": {"source_adapter": "chat", "source_external_id": "k1",
                       "author_type": "human", "author_id": "ml"}}


def test_run_vault_pass_promotes_an_approved_candidate():
    emitted = []
    # inject a `make` returning an in-memory promoter (no network) with an approval for k1.
    def make(palace_id, seat, *, now_ts, floors=None):
        return VaultPromoter(
            load_candidates=lambda: [dict(CAND)],
            approvals=lambda: {"k1": "promote"},
            emit=lambda rec: emitted.append(rec),
            promoted=InMemoryPromotedStore(),
            now_ts=now_ts)
    rows = vr.run_vault_pass("pal", ["aria"], now_ts="2026-02-01T00:00:00Z", make=make)
    assert rows[0]["seat"] == "aria" and rows[0]["promoted"] == 1, rows
    assert rows[0]["summary"]["promoted"] == 1
    assert emitted and emitted[0]["do_not_re_promote"] is True and emitted[0]["rollback_armed"] is True
    print("PASS test_run_vault_pass_promotes_an_approved_candidate")


def test_unapproved_candidate_holds_not_promoted():
    def make(palace_id, seat, *, now_ts, floors=None):
        return VaultPromoter(load_candidates=lambda: [dict(CAND)], approvals=lambda: {},  # no consent
                             emit=lambda rec: None, promoted=InMemoryPromotedStore(), now_ts=now_ts)
    rows = vr.run_vault_pass("pal", ["aria"], now_ts="t", make=make)
    assert rows[0]["promoted"] == 0 and rows[0]["summary"]["held"] == 1   # VL-4 needs_review
    print("PASS test_unapproved_candidate_holds_not_promoted")


def test_load_approvals_folds_human_verdicts():
    orig = m.get_run_events
    m.get_run_events = lambda tenant, seat, kind=None, limit=None: [
        {"proposal_id": "k1", "agreed": True}, {"proposal_id": "k2", "agreed": False},
        {"agreed": True},  # no proposal_id → skipped
    ] if kind == "human_verdict" else []
    try:
        assert vr.load_approvals("pal", "aria") == {"k1": "promote", "k2": "reject"}
    finally:
        m.get_run_events = orig
    print("PASS test_load_approvals_folds_human_verdicts")


def test_palace_promoted_store_inert_at_construction():
    # construction touches no network; only method calls do (lazy imports of the credential-gated seam).
    store = vr.PalacePromotedStore("pal", "aria")
    assert store.palace_id == "pal" and store.seat == "aria"
    print("PASS test_palace_promoted_store_inert_at_construction")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL VAULT RUNNER TESTS PASS")
