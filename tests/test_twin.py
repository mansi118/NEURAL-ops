"""Broker-level twin tests (versioning + schema), complementary to nrt.

Run: python3 tests/test_twin.py   (stdlib only, exits non-zero on failure).
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runtime.core import MemoryBroker  # noqa: E402
from runtime.twin import validate_twin, twin_preamble  # noqa: E402

DRAFT = {"identity": "founder", "communication": "terse", "decision_style": "risk-first",
         "body": "# decisions\nrisk-first", "signals": {"observed_decisions": 3}}


def test_versioning_and_signal_preservation():
    b = MemoryBroker("unit", [])
    a0 = b.put_twin("neuraledge", "aria", dict(DRAFT))
    assert a0["status"] == "ok" and a0["version"] == 0 and a0["maturity"] == "seed", a0
    # re-run on role change: new draft WITHOUT signals -> version bumps, signals preserved
    a1 = b.put_twin("neuraledge", "aria", {"identity": "founder/cto", "communication": "terse",
                                           "decision_style": "risk-first", "body": "# v2"})
    assert a1["version"] == 1, a1
    assert b.get_twin("neuraledge", "aria")["signals"] == {"observed_decisions": 3}, "signals must persist across re-run"
    print("PASS test_versioning_and_signal_preservation")


def test_stale_base_version_rejected():
    """Gate 5: optimistic concurrency — a write against a stale base_version is rejected."""
    b = MemoryBroker("unit", [])
    b.put_twin("neuraledge", "aria", dict(DRAFT))                 # -> version 0
    b.put_twin("neuraledge", "aria", dict(DRAFT, body="# v2"))    # -> version 1
    stale = b.put_twin("neuraledge", "aria", dict(DRAFT, body="# v3", base_version=0))
    assert stale["status"] == "rejected", stale
    assert {d["code"] for d in stale["diagnostics"]} == {"stale_base_version"}, stale
    fresh = b.put_twin("neuraledge", "aria", dict(DRAFT, body="# v3", base_version=1))
    assert fresh["status"] == "ok" and fresh["version"] == 2, fresh
    print("PASS test_stale_base_version_rejected")


def test_schema_rejects_incomplete():
    b = MemoryBroker("unit", [])
    bad = b.put_twin("neuraledge", "aria", {"identity": "x"})  # missing communication/decision_style
    assert bad["status"] == "rejected", bad
    codes = {d["code"] for d in bad["diagnostics"]}
    assert "twin_missing_field" in codes, bad
    print("PASS test_schema_rejects_incomplete")


def test_isolation_by_twin_id():
    b = MemoryBroker("unit", [], twin={"twin_id": "other-co:x", "version": 0, "maturity": "seed",
                                       "identity": "a", "communication": "b", "decision_style": "c"})
    assert b.get_twin("neuraledge", "aria") is None, "must not return another tenant:seat's twin"
    print("PASS test_isolation_by_twin_id")


def test_preamble():
    assert twin_preamble(None) == ""
    p = twin_preamble({"twin_id": "neuraledge:aria", "maturity": "seed", "body": "X"})
    assert "neuraledge:aria" in p and "X" in p
    print("PASS test_preamble")


if __name__ == "__main__":
    test_versioning_and_signal_preservation()
    test_stale_base_version_rejected()
    test_schema_rejects_incomplete()
    test_isolation_by_twin_id()
    test_preamble()
    print("ALL TWIN TESTS PASS")
