"""P4 — Hierarchy Resolver (org-chart delegation/escalation). Offline, stdlib. core untouched.
Run: python3 tests/test_hierarchy.py"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from acp import hierarchy as H  # noqa: E402


def _org():
    S = H.Seat
    return H.OrgChart(seats={
        "ceo":      S("ceo", "owner", None),
        "vp_eng":   S("vp_eng", "admin", "ceo", frozenset({"architecture"})),
        "eng1":     S("eng1", "member", "vp_eng", frozenset({"code"})),
        "eng2":     S("eng2", "member", "vp_eng", frozenset({"code", "deploy"})),
        "vp_sales": S("vp_sales", "admin", "ceo", frozenset({"pipeline"})),
    })


def test_escalate():
    org = _org()
    assert H.escalate("eng1", org) == "vp_eng"
    assert H.escalate("vp_eng", org) == "ceo"
    assert H.escalate("ceo", org) is None
    print("PASS test_escalate")


def test_escalation_chain():
    org = _org()
    assert H.escalation_chain("eng1", org) == ["vp_eng", "ceo"]
    assert H.escalation_chain("ceo", org) == []
    print("PASS test_escalation_chain")


def test_subordinates():
    org = _org()
    assert H.subordinates("ceo", org) == ["eng1", "eng2", "vp_eng", "vp_sales"]
    assert H.subordinates("vp_eng", org) == ["eng1", "eng2"]
    assert H.subordinates("eng1", org) == []
    print("PASS test_subordinates")


def test_delegate_nearest_capable_subordinate():
    org = _org()
    assert H.delegate("code", "ceo", org) == "eng1"        # both eng have it; tie → sorted
    assert H.delegate("deploy", "ceo", org) == "eng2"      # only eng2
    assert H.delegate("architecture", "ceo", org) == "vp_eng"
    print("PASS test_delegate_nearest_capable_subordinate")


def test_delegate_none_when_no_subordinate_holds_it():
    org = _org()
    assert H.delegate("pipeline", "vp_eng", org) is None   # vp_eng's subtree lacks pipeline → escalate
    assert H.delegate("code", "eng1", org) is None         # no subordinates at all
    print("PASS test_delegate_none_when_no_subordinate_holds_it")


def test_validation_rejects_cycles_and_bad_refs():
    S = H.Seat
    try:
        H.OrgChart(seats={"a": S("a", "m", "b"), "b": S("b", "m", "a")}); assert False
    except H.HierarchyError:
        pass
    try:
        H.OrgChart(seats={"a": S("a", "m", "ghost")}); assert False
    except H.HierarchyError:
        pass
    try:
        H.escalate("nobody", _org()); assert False
    except H.HierarchyError:
        pass
    print("PASS test_validation_rejects_cycles_and_bad_refs")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL HIERARCHY TESTS PASS")
