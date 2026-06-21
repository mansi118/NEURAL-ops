"""P2 — twin keyed per-USER (requester), not per-NEop (seat). Offline. core.py sanctioned change.
Run: python3 tests/test_twin_keying.py   (docs/decisions/twin-keying.md)

Proves: the twin is keyed by the server-derived `requester` when present (one twin shared across ALL of
a user's NEops), falling back to `seat` only for genuinely user-less runs. Working memory stays per-seat.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runtime.core import dispatch  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
HR = str(ROOT / "agents" / "hierarchy-resolver")   # twin:{read}
VP = str(ROOT / "agents" / "vault-promoter")        # twin:{read}, different NEop
TC = str(ROOT / "agents" / "twin-curator")          # twin:{read, write}

CASS_HR = {"plan:x": {"tasks": [{"task_id": "t", "tool": "resolve_hierarchy", "depends_on": []}]}, "verify:x": {"pass": True}}
CASS_VP = {"plan:x": {"tasks": [{"task_id": "t", "tool": "vault_promote", "depends_on": []}]}, "verify:x": {"pass": True}}
CASS_TC = {"plan:x": {"tasks": [{"task_id": "t", "tool": "curate_twin", "depends_on": []}]}, "verify:x": {"pass": True}}


def _twin(owner):
    return {"twin_id": f"neuraledge:{owner}", "version": 1, "maturity": "seed",
            "identity": "U", "communication": "c", "decision_style": "d"}


def _assembled(res):
    return [e for e in res["events"] if e["event"] == "twin_assembled"]


def test_read_keyed_by_requester_not_seat():
    msg = {"text": "hi", "tenant": "neuraledge", "seat": "hierarchy-resolver", "requester": "userU"}
    res = dispatch(HR, msg, "unit", CASS_HR, {"resolve_hierarchy": {}}, [], twin=_twin("userU"))
    ev = _assembled(res)
    assert ev and ev[0]["twin_id"] == "neuraledge:userU", res["state"]
    print("PASS test_read_keyed_by_requester_not_seat")


def test_two_distinct_neops_same_requester_share_one_twin():
    tw = _twin("userU")
    a = dispatch(HR, {"text": "h", "tenant": "neuraledge", "seat": "hierarchy-resolver", "requester": "userU"},
                 "unit", CASS_HR, {"resolve_hierarchy": {}}, [], twin=tw)
    b = dispatch(VP, {"text": "h", "tenant": "neuraledge", "seat": "vault-promoter", "requester": "userU"},
                 "unit", CASS_VP, {"vault_promote": {}}, [], twin=tw)
    assert _assembled(a) and _assembled(a)[0]["twin_id"] == "neuraledge:userU"
    assert _assembled(b) and _assembled(b)[0]["twin_id"] == "neuraledge:userU"   # SAME twin, different NEop
    print("PASS test_two_distinct_neops_same_requester_share_one_twin")


def test_no_requester_falls_back_to_seat():
    # No requester ⇒ keyed by seat (the NEop). The user twin is NOT visible; the seat twin IS. (regression)
    msg = {"text": "h", "tenant": "neuraledge", "seat": "hierarchy-resolver"}
    seat_twin = dispatch(HR, msg, "unit", CASS_HR, {"resolve_hierarchy": {}}, [], twin=_twin("hierarchy-resolver"))
    user_twin = dispatch(HR, msg, "unit", CASS_HR, {"resolve_hierarchy": {}}, [], twin=_twin("userU"))
    assert _assembled(seat_twin), "seat-keyed twin must be read when no requester"
    assert not _assembled(user_twin), "a user twin must NOT be visible without the requester"
    print("PASS test_no_requester_falls_back_to_seat")


def test_write_keyed_by_requester():
    # A twin-writing NEop with requester=userU writes the USER's twin, not its own.
    msg = {"text": "h", "tenant": "neuraledge", "seat": "twin-curator", "requester": "userU"}
    draft = {"identity": "U", "communication": "c", "decision_style": "d"}
    res = dispatch(TC, msg, "unit", CASS_TC, {"curate_twin": draft}, [], twin=None)
    tw_written = [e for e in res["events"] if e["event"] == "twin_written"]
    assert res["state"] == "DONE", res["state"]
    assert tw_written and tw_written[0]["seat"] == "userU", tw_written
    assert res["twin_written"]["twin_id"] == "neuraledge:userU"
    print("PASS test_write_keyed_by_requester")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL TWIN-KEYING TESTS PASS")
