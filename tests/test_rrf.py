"""RRF fusion (S2 §2.5) — five gates, all proven incl. the negatives. Pure; core.py untouched.

Unit fixtures are recorded multi-signal lists in fixtures/rrf/ (no network). Gates:
  1 exact fusion math      — score = Σ 1/(rrf_k+rank) matches hand-computed values + order
  2 determinism/tie-break  — same input -> same output (x3); equal scores break by chunk_id
  3 single-list = identity  — one signal in == that order out (NO reorder); the safe-case no-op
  4 missing-signal          — chunk absent from some lists / an empty signal -> fuse remainder, no crash
  5 contract + provenance   — {chunks, provenance} shape; provenance retained per chunk + aligned; top-k
Run: python3 tests/test_rrf.py
"""
import json, sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.rrf import fuse, fuse_results, RRF_K  # noqa: E402

FX = json.loads((R / "fixtures" / "rrf" / "multi_signal.json").read_text())
SIGNALS = FX["signals"]                              # list of signal lists of chunk dicts
ID_LISTS = [[c["id"] for c in lst] for lst in SIGNALS]


def test_gate1_exact_fusion_math():
    fused = fuse(ID_LISTS, rrf_k=FX["rrf_k"])
    assert [cid for cid, _ in fused] == FX["expected_order"], fused
    assert {cid: sc for cid, sc in fused} == FX["expected_scores"], fused
    # independently recompute c2 from the formula (vector#2 + bm25#1 + graph#1)
    assert dict(fused)["c2"] == round(1/(RRF_K+2) + 1/(RRF_K+1) + 1/(RRF_K+1), 6), fused
    print("PASS test_gate1_exact_fusion_math")


def test_gate2_determinism_and_tiebreak():
    a = fuse(ID_LISTS); b = fuse(ID_LISTS); c = fuse(ID_LISTS)
    assert a == b == c, (a, b, c)                                   # determinism x3
    tie = fuse([["b"], ["a"]])                                      # each id once at rank1 -> equal score
    assert [cid for cid, _ in tie] == ["a", "b"], tie              # tie broken by chunk_id asc
    assert tie[0][1] == tie[1][1], tie
    print("PASS test_gate2_determinism_and_tiebreak")


def test_gate3_single_list_is_identity():
    order = ["c1", "c2", "c3"]
    assert [cid for cid, _ in fuse([order])] == order              # NO reorder of a one-signal list
    single = fuse_results([SIGNALS[0]], k=10)
    assert [c["id"] for c in single["chunks"]] == [c["id"] for c in SIGNALS[0]], single
    print("PASS test_gate3_single_list_is_identity")


def test_gate4_missing_signal_fuses_remainder():
    with_empty = fuse([ID_LISTS[0], [], ID_LISTS[1]])             # an empty signal -> skipped, no crash
    assert [cid for cid, _ in with_empty][0] in ("c1", "c2"), with_empty
    assert any(cid == "c3" for cid, _ in with_empty)              # c3 (only in list 0) still present
    subset = fuse(ID_LISTS[:2])                                    # drop graph+recency -> fuse remainder
    assert {cid for cid, _ in subset} == {"c1", "c2", "c3"}, subset
    assert fuse([[], []]) == [] and fuse_results([[], []]) == {"chunks": [], "provenance": []}
    print("PASS test_gate4_missing_signal_fuses_remainder")


def test_gate5_contract_and_provenance_preserved():
    out = fuse_results(SIGNALS, k=5, rrf_k=FX["rrf_k"])
    assert set(out) == {"chunks", "provenance"}, out               # contract shape unchanged
    assert [c["id"] for c in out["chunks"]] == FX["expected_order"], out
    # c1's provenance lived ONLY in the vector signal — it must survive the merge + fusion
    c1 = next(c for c in out["chunks"] if c["id"] == "c1")
    assert c1["provenance"] == {"id": "c1", "source_adapter": "mcp", "created_at": 1700000001}, c1
    assert "rrf_score" in c1, c1
    # provenance list is aligned 1:1 to fused chunk order
    assert out["provenance"] == [c.get("provenance") for c in out["chunks"]], out
    # top-k respected
    assert len(fuse_results(SIGNALS, k=2)["chunks"]) == 2
    print("PASS test_gate5_contract_and_provenance_preserved")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL RRF TESTS PASS")
