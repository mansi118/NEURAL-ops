"""Runtime unit tests (broker-level), complementary to nrt's agent-level tests.

nrt tests whole NEop runs; these test the brokers directly where a single agent run
can't reach (e.g. two writes in one broker instance). Stdlib only, no pytest.
Run: python3 tests/test_memory.py   (exits non-zero on failure).
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runtime.core import MemoryBroker  # noqa: E402


def test_dedup_idempotent():
    """Refinement #2: two identical writes -> same dedup_key, second is a noop, no dupe."""
    b = MemoryBroker("unit", [])
    rec = {"content": "X", "cites": ["c1"], "category": "run"}
    r1 = b.write("neuraledge", "aria", rec)
    r2 = b.write("neuraledge", "aria", dict(rec))  # identical content
    assert r1["dedup_key"] == r2["dedup_key"], "identical writes must share a dedup_key"
    assert r1["status"] == "ok" and r2["status"] == "noop", "second identical write must noop"
    assert len(b.writes) == 1, "duplicate must not be stored twice"
    r3 = b.write("neuraledge", "aria", {"content": "Y", "cites": ["c1"], "category": "run"})
    assert r3["dedup_key"] != r1["dedup_key"], "different content must yield a different key"
    assert len(b.writes) == 2, "distinct record must be stored"
    print("PASS test_dedup_idempotent")


def test_tenant_guard():
    """A seat in tenant A must never see tenant B's chunks."""
    bundle = {"chunks": [{"id": "c1", "tenant": "neuraledge", "text": "ok"},
                         {"id": "cB", "tenant": "other-co", "text": "secret"}],
              "provenance": []}
    out = MemoryBroker("unit", [], bundle=bundle).retrieve("neuraledge", "aria", "q")
    ids = [c["id"] for c in out["chunks"]]
    assert ids == ["c1"], f"tenant guard failed, leaked: {ids}"
    print("PASS test_tenant_guard")


if __name__ == "__main__":
    test_dedup_idempotent()
    test_tenant_guard()
    print("ALL RUNTIME UNIT TESTS PASS")
