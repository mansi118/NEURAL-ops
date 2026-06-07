"""RRF / hybrid retrieval tests (Phase D) — pure, offline-gradeable; core.py untouched.

Proves the canonical RRF property (strong-on-both beats strong-on-one), exact scores, weighting,
in-list dedup, deterministic tie-break, and the hybrid (vector + lexical) fusion the live memory
path uses. Run: python3 tests/test_retrieval.py
"""
import sys, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from runtime.retrieval import rrf_fuse, lexical_rank, hybrid_rank, RRF_K  # noqa: E402


def test_rrf_core_property():
    # 'b' is high in BOTH lists; 'a'/'c' are high in only one -> b must win.
    fused = rrf_fuse([["a", "b", "c"], ["b", "c", "a"]])
    assert [s["item"] for s in fused][0] == "b", fused
    assert fused[0]["ranks"] == {0: 2, 1: 1}, fused
    print("PASS test_rrf_core_property")


def test_rrf_exact_scores():
    fused = {s["item"]: s["score"] for s in rrf_fuse([["a", "b", "c"], ["b", "c", "a"]])}
    assert fused["b"] == round(1/(RRF_K+2) + 1/(RRF_K+1), 6), fused
    assert fused["a"] == round(1/(RRF_K+1) + 1/(RRF_K+3), 6), fused
    assert fused["b"] > fused["a"] > fused["c"], fused          # full ordering
    print("PASS test_rrf_exact_scores")


def test_rrf_weights_shift_order():
    # list-0 ranks 'x' #1, list-1 ranks 'y' #1. Equal weights -> tie -> key tie-break puts x first.
    lists = [["x"], ["y"]]
    assert [s["item"] for s in rrf_fuse(lists)] == ["x", "y"], rrf_fuse(lists)
    # weight list-1 heavily -> 'y' overtakes 'x'.
    assert [s["item"] for s in rrf_fuse(lists, weights=[1.0, 5.0])] == ["y", "x"]
    print("PASS test_rrf_weights_shift_order")


def test_rrf_dedupe_in_list_keeps_best_rank():
    # 'a' appears twice in one list (rank 1 and 3) -> only the best (rank 1) counts.
    one = rrf_fuse([["a", "b", "a"]])
    by = {s["item"]: s for s in one}
    assert by["a"]["ranks"] == {0: 1} and by["a"]["score"] == round(1/(RRF_K+1), 6), one
    print("PASS test_rrf_dedupe_in_list_keeps_best_rank")


def test_rrf_determinism_and_weight_guard():
    lists = [["a", "b"], ["b", "a"]]
    assert rrf_fuse(lists) == rrf_fuse(lists)                    # same input -> same output
    try:
        rrf_fuse(lists, weights=[1.0])                           # mismatched length -> raise
        assert False, "expected ValueError"
    except ValueError:
        pass
    print("PASS test_rrf_determinism_and_weight_guard")


def test_lexical_rank():
    chunks = [{"id": "1", "text": "embedding model voyage"},
              {"id": "2", "text": "the zoo media retainer was signed"},
              {"id": "3", "text": "voyage embedding dimensions and the model"}]
    ranked = [c["id"] for c in lexical_rank("embedding model", chunks)]
    assert ranked[0] in ("1", "3") and "2" == ranked[-1], ranked   # overlap wins; no-overlap last
    assert [c["id"] for c in lexical_rank("", chunks)] == ["1", "2", "3"]  # empty query -> input order
    print("PASS test_lexical_rank")


def test_hybrid_rank_fuses_vector_and_lexical():
    # vector order = given order (v1 top). v1 has NO lexical overlap; v2 is vector-2nd but
    # lexical-1st; v3 is vector-3rd, lexical-2nd. Fusion must lift v2 above the vector-top v1.
    chunks = [{"id": "v1", "text": "quarterly revenue numbers"},          # vec 1, lex last (0 overlap)
              {"id": "v2", "text": "embedding model voyage dimensions"},  # vec 2, lex 1 (3 overlap)
              {"id": "v3", "text": "voyage model"}]                       # vec 3, lex 2 (2 overlap)
    out = hybrid_rank("embedding model voyage", chunks)
    order = [c["id"] for c in out]
    assert order[0] == "v2", order                              # strong-on-both beats vector-top
    assert order.index("v2") < order.index("v1"), order        # fusion CHANGED the vector ordering
    assert out[0]["rrf_ranks"] == {"vector": 2, "lexical": 1}, out[0]
    assert "rrf_score" in out[0], out[0]
    assert hybrid_rank("q", []) == []                          # empty -> empty
    print("PASS test_hybrid_rank_fuses_vector_and_lexical")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL RETRIEVAL TESTS PASS")
