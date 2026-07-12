"""Shadow-mode fidelity runner (Track 3 driver) — the RUNNABLE cadence that folds a seat's
finished-run shadow predictions into its twin, behind the same injected seams as the harness.

`runtime/fidelity_harness.py` is the pure loop (`FidelityLoop` over `load_twin` / `save_twin` /
`load_events` + an optional judge). This module is only the DRIVER + the LIVE seams + a pluggable
score sink — nothing here re-implements the loop or the grader. It supplies:

  - PalaceFidelitySeams — the live I/O for `FidelityLoop`: `load_events` reads a seat's
    `shadow_prediction` run-log rows off the Convex SoT; `load_twin` / `save_twin` are the palace
    twin read/upsert. Every method reuses `runtime.memory._post` (lazy-imported INSIDE the method),
    so it inherits the credential gate + the L4 fail-closed scope guard and only touches the network
    on live use — same posture as `acp`'s ConvexSnapshotStore. palaceId is baked at construction
    (the tenant); the seat is passed explicitly per call and IS the address for the twin/event rows.
    Scope is NEVER taken from the model.

  - ScoreSink — a one-method (`write(tenant, seat, record)`) seam for the fidelity observability
    stream. LocalFileScoreSink appends JSONL to a path (pure; wall-clock is the sink's concern via an
    injected `now`). ClickHouseScoreSink is a documented SEAM that raises until Track 2 lands.

  - run_shadow_pass — ticks the loop per seat and writes the honest breakdown + fidelity score to the
    sink for EVERY seat (observability), while twin persistence stays governed by the harness's
    should_persist. SHADOW-MODE INVARIANT: this driver never blocks, gates, or mutates anything live
    beyond writing the seat's twin (via the loop) and its score (via the sink). There is no "block"
    path here — shadow mode only observes.

No wall-clock and no I/O in the pure paths; the network is entirely inside the lazy `_post`. The
nightly / EventBridge cadence that invokes the CLI is a scheduling concern, not logic. core.py is
untouched.
"""
from __future__ import annotations

import json


# --- live seams for FidelityLoop (Convex SoT) ---------------------------------------
# Provenance-not-assertion, same discipline as acp.approval_gate.ConvexSnapshotStore: palaceId is
# BAKED (the tenant), the seat is passed explicitly, and the server keys each row by (palaceId,
# neopId). The FidelityLoop-supplied `tenant` is the driver's own tenant (== the baked palaceId, by
# construction in run_shadow_pass / the CLI); the baked id is authoritative so scope can never be
# substituted from below. Nothing here imports or dials the network at construction — only on a
# method call (lazy `from runtime.memory import ...`), which also enforces the credential gate.

class PalaceFidelitySeams:
    """Live `FidelityLoop` seams over the Convex palace. Drop-in for the in-memory offline seams:
    exposes `load_events(tenant, seat)`, `load_twin(tenant, seat)`, `save_twin(tenant, seat, twin)`.

    LIVE SEAM TOOL NAMES (reconciled with the palace `/mcp` dispatch):
      - load_events reuses `runtime.memory.get_run_events` → `palace_get_run_events`, the INTERIM
        run-log store (palace #31): finished-run shadow_prediction rows for (palaceId, neopId),
        newest-first + bounded. INTERIM by design — the durable event corpus migrates to ClickHouse
        when the comms tier lands (Track 2). Each row is a core.py shadow_prediction shape
        ({kind|type, predicted, actual, class}).
      - twin read/upsert reuse the EXISTING `runtime.memory.get_twin` / `put_twin` (which post
        `palace_get_twin` / `palace_put_twin` and own the twin marshalling) — not re-implemented here.
    """

    def __init__(self, palace_id):
        self.palace_id = palace_id

    def load_events(self, tenant, seat):
        """Read a seat's finished-run events off the palace run-log (INTERIM store) — BOTH machine
        shadow_prediction AND human_verdict rows (no kind filter), so the honest blended fidelity
        (machine + authoritative human) folds in one pass. `signals_from_events` routes by event kind
        and ignores anything else. Network only on live use (lazy, credential-gated memory seam)."""
        from runtime.memory import get_run_events   # lazy: credential + L4 scope gate only on live use
        return get_run_events(self.palace_id, seat)

    def load_twin(self, tenant, seat):
        """Read-by-address twin (palace_get_twin) or None. Reuses the canonical memory seam."""
        from runtime.memory import get_twin
        return get_twin(self.palace_id, seat)

    def save_twin(self, tenant, seat, twin):
        """Blind upsert (palace_put_twin, latest wins). Reuses the canonical memory seam."""
        from runtime.memory import put_twin
        return put_twin(self.palace_id, seat, twin)


# --- score sink seam ----------------------------------------------------------------

class ScoreSink:
    """The fidelity observability sink — one method, `write(tenant, seat, record)`. Offline it is an
    in-memory list or a JSONL file; live (Track 2) it is a columnar store. Kept as a seam so the
    driver never couples to a backend."""

    def write(self, tenant, seat, record):
        raise NotImplementedError


class LocalFileScoreSink(ScoreSink):
    """Append each fidelity record as one JSON line to `path`. Pure given `now`: the wall-clock is the
    SINK's concern — pass `now() -> str` to stamp each row with an `at` field (EventBridge/cron injects
    the tick time); with no `now`, rows carry no timestamp and the logic stays deterministic."""

    def __init__(self, path, *, now=None):
        self.path = str(path)
        self.now = now

    def write(self, tenant, seat, record):
        row = {"tenant": tenant, "seat": seat, **record}
        if self.now is not None:
            row["at"] = self.now()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
        return row


class ClickHouseScoreSink(ScoreSink):
    """SEAM ONLY — the columnar fidelity stream lands when Track 2 (`enable_comms_tier`) applies and a
    ClickHouse cluster is deployed. Not implemented: there is no client to build against yet, and a
    stub that silently swallowed rows would be a fake green. It raises on `write` so a live wiring
    mistake is loud, not lossy."""

    def __init__(self, *args, **kwargs):
        self._args = (args, kwargs)

    def write(self, tenant, seat, record):
        raise NotImplementedError(
            "ClickHouseScoreSink is a Track-2 seam (enable_comms_tier) — no ClickHouse cluster is "
            "deployed. Inject a LocalFileScoreSink (or a live sink) until Track 2 ships.")


# --- driver -------------------------------------------------------------------------

def _record(seat, result):
    """The honest per-seat observability record: the blended fidelity score PLUS the full breakdown
    (blended / human-only / machine-only), so the day-90 metric is never read as a single inflated
    number. `fidelity` here == `curator.fidelity` for the graded signals (harness contract)."""
    return {
        "seat": seat,
        "fidelity": result.get("fidelity"),
        "maturity": result.get("maturity"),
        "scored": result.get("scored"),
        "persisted": result.get("persisted"),
        "breakdown": result.get("breakdown"),
    }


def run_shadow_pass(loop, tenant, seats, sink, *, sustained_days=0, window=None):
    """One shadow-mode pass: tick `loop` for each seat and write its fidelity record to `sink`.

    The score is recorded for EVERY seat (observability — mirroring should_persist's intent to surface
    a moved score), while whether the TWIN is persisted stays the harness's decision inside `tick`.
    Returns the list of written records (also handy for the CLI to print a summary).

    SHADOW-MODE INVARIANT: nothing here blocks, gates, or mutates any live state beyond (a) the twin
    write the loop already governs and (b) the score write to the sink. There is deliberately no
    approval/deny path — shadow mode only observes."""
    records = []
    for seat in seats:
        result = loop.tick(tenant, seat, sustained_days=sustained_days, window=window)
        rec = _record(seat, result)
        sink.write(tenant, seat, rec)
        records.append(rec)
    return records


# --- CLI entrypoint (EventBridge/cron invokes this) ---------------------------------

def _seams_from_env(env):
    """Construct the live seams + loop from env (integration-mode). PALACE_ID is baked; seats come
    from FIDELITY_SEATS (comma-separated). The JUDGE is Claude Haiku on Bedrock (NOT Nova) — the cheap
    fast tier of the Haiku+Sonnet standard, wired via `runtime.judge.make_judge(converse_invoke())`.
    It is enabled only when AWS_BEARER_TOKEN_BEDROCK is set (fail-closed on a blank token); with no
    token the judge is None, so a live cadence runs the free lexical/exact grader and leaves the
    ambiguous middle UNSCORED (never fabricated). FIDELITY_JUDGE_MODEL overrides the model. Building the
    judge is inert (no network) — the Converse call happens only when the grader consults it."""
    from runtime.fidelity_harness import FidelityLoop
    from runtime.judge import make_judge
    from runtime.bedrock import converse_invoke, DEFAULT_JUDGE_MODEL
    palace_id = (env.get("PALACE_ID") or "").strip()
    if not palace_id:
        raise SystemExit("PALACE_ID is required (the tenant/palaceId to run the shadow pass for)")
    seats = [s.strip() for s in (env.get("FIDELITY_SEATS") or "").split(",") if s.strip()]
    if not seats:
        raise SystemExit("FIDELITY_SEATS is required (comma-separated seat/neopId list)")
    bearer = (env.get("AWS_BEARER_TOKEN_BEDROCK") or "").strip()
    judge = make_judge(converse_invoke(model_id=env.get("FIDELITY_JUDGE_MODEL") or DEFAULT_JUDGE_MODEL)) \
        if bearer else None
    seams = PalaceFidelitySeams(palace_id)
    loop = FidelityLoop(seams.load_twin, seams.save_twin, seams.load_events, judge=judge)
    return loop, palace_id, seats


def main(argv=None):
    import argparse
    import os
    p = argparse.ArgumentParser(description="Shadow-mode fidelity runner — one pass over a tenant's seats.")
    p.add_argument("--out", default=os.environ.get("FIDELITY_SCORE_LOG", "fidelity_scores.jsonl"),
                   help="JSONL score-sink path (LocalFileScoreSink).")
    p.add_argument("--sustained-days", type=int, default=int(os.environ.get("FIDELITY_SUSTAINED_DAYS", "0")),
                   help="Days the growing->mature fidelity floor has held (scheduling supplies this).")
    p.add_argument("--window", type=int, default=None,
                   help="Trailing signal-count window (volume bound); omit for all.")
    args = p.parse_args(argv)

    loop, tenant, seats = _seams_from_env(os.environ)
    import datetime
    sink = LocalFileScoreSink(args.out, now=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    records = run_shadow_pass(loop, tenant, seats, sink,
                              sustained_days=args.sustained_days, window=args.window)
    for r in records:
        print(json.dumps({"seat": r["seat"], "fidelity": r["fidelity"],
                          "maturity": r["maturity"], "scored": r["scored"],
                          "persisted": r["persisted"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
