"""Reciprocal Rank Fusion (Phase D) — fuse multiple ranked lists into one robust ranking.

Pure + deterministic; core.py untouched. The memory seam's live backend returns a single
vector-ranked list; this adds a client-side LEXICAL ranking over the SAME candidates and
RRF-fuses the two (classic hybrid search), so a chunk strong on BOTH signals outranks one
strong on only one. RRF is rank-based — it ignores raw score scales — which is exactly why
it can fuse a cosine similarity with a token-overlap count without normalizing units.

  RRF score for doc d:   sum over lists  weight_l / (K + rank_l(d))     (rank 1-based; K=60)

K=60 is the canonical constant (Cormack et al.): large enough that the gap between ranks 1
and 2 doesn't dominate, small enough that deep ranks still matter.
"""
from __future__ import annotations
import re

RRF_K = 60


def rrf_fuse(ranked_lists, *, key=None, k=RRF_K, weights=None):
    """Fuse ordered lists (best-first) into one ranking. Pure + deterministic.

    Returns [{item, score, ranks}] sorted by score desc, ties broken by str(key) asc.
    `key` maps an item to its identity (default identity); `ranks` is {list_index: best_rank}.
    A repeated id within one list keeps its best (lowest) rank. weights default to 1.0 each.
    """
    key = key or (lambda x: x)
    n = len(ranked_lists)
    weights = list(weights) if weights is not None else [1.0] * n
    if len(weights) != n:
        raise ValueError(f"weights length {len(weights)} != {n} ranked_lists")

    agg = {}   # id -> {"item", "score", "ranks": {list_idx: rank}}
    for li, (lst, w) in enumerate(zip(ranked_lists, weights)):
        for rank, item in enumerate(lst, start=1):
            kk = key(item)
            slot = agg.setdefault(kk, {"item": item, "score": 0.0, "ranks": {}})
            prev = slot["ranks"].get(li)
            if prev is None:
                slot["ranks"][li] = rank
                slot["score"] += w / (k + rank)
            elif rank < prev:                       # better occurrence in same list -> upgrade
                slot["score"] += w * (1.0 / (k + rank) - 1.0 / (k + prev))
                slot["ranks"][li] = rank
    ordered = sorted(agg.values(), key=lambda s: (-s["score"], str(key(s["item"]))))
    for s in ordered:
        s["score"] = round(s["score"], 6)
    return ordered


def _tokens(s):
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def lexical_rank(query, chunks, *, text=lambda c: c.get("text", ""), key=lambda c: c.get("id")):
    """Length-normalized token-overlap ranking of chunks for a query (lightweight BM25-ish).

    Best-first; deterministic tie-break by str(key). An empty query returns the input order
    unchanged (no lexical signal -> defer to whatever order came in).
    """
    q = _tokens(query)
    if not q:
        return list(chunks)
    qset = set(q)

    def score(c):
        toks = _tokens(text(c))
        if not toks:
            return 0.0
        tf = sum(1 for t in toks if t in qset)
        return tf / (len(toks) ** 0.5)            # length-normalized term frequency

    return sorted(chunks, key=lambda c: (-score(c), str(key(c))))


def hybrid_rank(query, chunks, *, k=RRF_K, weights=None,
                text=lambda c: c.get("text", ""), key=lambda c: c.get("id")):
    """Hybrid retrieval: RRF-fuse the backend's vector order (chunks as given) with a
    client-side lexical re-rank of the SAME chunks. Returns chunks reordered, each annotated
    with `rrf_score` and `rrf_ranks` {vector, lexical}. weights = (vector_weight, lexical_weight).
    """
    if not chunks:
        return []
    vector_list = list(chunks)                     # backend already returned these vector-ranked
    lexical_list = lexical_rank(query, chunks, text=text, key=key)
    fused = rrf_fuse([vector_list, lexical_list], key=key, k=k, weights=weights)
    out = []
    for s in fused:
        c = dict(s["item"])
        c["rrf_score"] = s["score"]
        c["rrf_ranks"] = {"vector": s["ranks"].get(0), "lexical": s["ranks"].get(1)}
        out.append(c)
    return out
