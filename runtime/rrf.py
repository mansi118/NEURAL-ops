"""Reciprocal Rank Fusion (S2 §2.5) — pure, deterministic, no I/O.

The canonical fusion primitive. S2 §2.5 specifies retrieval as a fan-out across four channels
(vector · BM25 · graph multi-hop · recency) merged by RRF *without* per-channel weight tuning:

    score(chunk) = Σ over signal lists  1 / (rrf_k + rank)        (1-based rank; rrf_k ≈ 60)

The four signal sources live in the backend (Convex + FalkorDB/Graphiti), so the four-backend
fan-out ultimately belongs server-side and the broker passes through. This primitive is built
client-side because the math is identical wherever it runs (portable into nc-palace verbatim)
and the broker still fuses lists it holds separately (e.g. STM cache + LTM/Vault bundle).

`rrf_k` is named distinctly from the top-k `k` (result count) on purpose — they never collide.
core.py is untouched; this is a leaf module with no imports and no I/O.
"""
from __future__ import annotations

RRF_K = 60


def fuse(ranked_lists, rrf_k=RRF_K):
    """RRF over ranked lists of chunk_ids. Returns [(chunk_id, score)] sorted by score desc,
    ties broken by str(chunk_id) ascending (deterministic). Pure — no I/O.

    A single list in == that list's order out (each rank's score strictly decreases, so the
    sort is a no-op). A chunk absent from a list simply doesn't accrue that list's term. Within
    one list a repeated id keeps its first (best) rank — a malformed list can't double-count.
    """
    scores = {}
    for lst in ranked_lists:
        seen = set()
        for rank, cid in enumerate(lst, start=1):
            if cid in seen:                       # one rank per list (best occurrence wins)
                continue
            seen.add(cid)
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
    return sorted(((cid, round(s, 6)) for cid, s in scores.items()),
                  key=lambda t: (-t[1], str(t[0])))


def fuse_results(signal_lists, k=5, rrf_k=RRF_K):
    """Fuse ranked signal lists of chunk DICTS (each carries 'id', optionally 'provenance').

    Returns {chunks, provenance}: the fused top-`k` chunks (each annotated with `rrf_score`, its
    provenance retained) and a provenance list aligned 1:1 to that order. A chunk seen in several
    signals is merged (first non-null field wins) so partial signals still yield a full chunk.
    Pure — no network. Empty signal lists are skipped; an all-empty input yields empty results.
    """
    by_id, id_lists = {}, []
    for lst in signal_lists:
        ids = []
        for c in lst:
            cid = c.get("id")
            ids.append(cid)
            if cid not in by_id:
                by_id[cid] = dict(c)
            else:
                for kk, vv in c.items():
                    by_id[cid].setdefault(kk, vv)     # fill gaps from other signals
        id_lists.append(ids)

    chunks, provenance = [], []
    for cid, score in fuse(id_lists, rrf_k=rrf_k)[:k]:
        c = dict(by_id[cid])
        c["rrf_score"] = score
        chunks.append(c)
        provenance.append(c.get("provenance"))        # retained per chunk + aligned to order
    return {"chunks": chunks, "provenance": provenance}
