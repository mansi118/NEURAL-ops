"""Vault runner (Track 3 driver) — the RUNNABLE nightly cadence that promotes candidate memory writes
through VaultPromoter's five gates, behind the same injected seams as the harness.

`runtime/vault_harness.py` is the pure driver (VaultPromoter over load_candidates / approvals / emit /
promoted). This module is only the LIVE seams + a CLI — nothing re-implements the gates. It composes the
infra already built:
  - load_candidates → memory.get_run_events(kind="memory_candidate")  (REUSE the run_events store; a
    write-trigger persisting broker candidate writes as kind="memory_candidate" is the paired follow-up,
    same pattern as the verdict write-trigger).
  - approvals      → memory.get_run_events(kind="human_verdict") folded to {key -> promote|reject}. By
    CONTRACT the Decision-Queue proposal_id for a vault proposal == the candidate key (source_external_id).
  - promoted       → PalacePromotedStore over palace_is_promoted/mark_promoted/clear_promoted (#32) —
    the cross-pass do-not-re-promote store (contains/add/discard) run_events can't provide.
  - emit           → memory.write (palace_remember) — the durable closet sink for a promoted record.

PURE over the injected seams; network only inside memory._post (credential + L4 scope gated). No
wall-clock in the logic — now_ts is injected. core.py untouched.
"""
from __future__ import annotations

from runtime.vault_harness import VaultPromoter


# --- live seams over the palace (own-seat, credential-gated) -------------------------

class PalacePromotedStore:
    """The VaultPromoter `promoted` seam over the palace vault_promoted markers (#32). Same
    contains/add/discard interface as InMemoryPromotedStore, but durable across ticks. palaceId + seat
    are baked; the server keys each marker by (palaceId, neopId, key). Network only on a method call."""

    def __init__(self, palace_id, seat):
        self.palace_id = palace_id
        self.seat = seat

    def __contains__(self, key):
        from runtime.memory import is_promoted   # lazy: credential + scope gate only on live use
        return is_promoted(self.palace_id, self.seat, key)

    def add(self, key):
        from runtime.memory import mark_promoted
        mark_promoted(self.palace_id, self.seat, key)

    def discard(self, key):
        from runtime.memory import clear_promoted
        clear_promoted(self.palace_id, self.seat, key)


def load_candidates(palace_id, seat, limit=None):
    """Candidate memory writes for a seat — read from the run_events store (kind=memory_candidate)."""
    from runtime.memory import get_run_events
    return get_run_events(palace_id, seat, kind="memory_candidate", limit=limit)


def load_approvals(palace_id, seat):
    """Fold this seat's human_verdict run-events → {key -> 'promote'|'reject'} (the Decision-Queue
    consent for VL-4). By contract a vault proposal's id == the candidate key (source_external_id)."""
    from runtime.memory import get_run_events
    out = {}
    for ev in get_run_events(palace_id, seat, kind="human_verdict"):
        key = (ev or {}).get("proposal_id")
        if key is not None:
            out[key] = "promote" if ev.get("agreed") else "reject"
    return out


def emit_promoted(palace_id, seat, record):
    """Durable sink for a promoted (redacted, rollback-armed) record — palace_remember (a closet)."""
    from runtime.memory import write
    return write(palace_id, seat, record)


def make_promoter(palace_id, seat, *, now_ts, floors=None):
    """Wire a VaultPromoter over the live palace seams for one seat."""
    return VaultPromoter(
        load_candidates=lambda: load_candidates(palace_id, seat),
        approvals=lambda: load_approvals(palace_id, seat),
        emit=lambda record: emit_promoted(palace_id, seat, record),
        promoted=PalacePromotedStore(palace_id, seat),
        floors=floors,
        now_ts=now_ts,
    )


# --- driver -------------------------------------------------------------------------

def run_vault_pass(palace_id, seats, *, now_ts, floors=None, make=make_promoter):
    """One vault cadence pass: tick a VaultPromoter per seat, collect the per-seat summaries. `make` is
    injectable so the driver is unit-testable with an in-memory promoter (no network)."""
    results = []
    for seat in seats:
        promoter = make(palace_id, seat, now_ts=now_ts, floors=floors)
        result = promoter.tick(now_ts=now_ts)
        results.append({"seat": seat, "summary": result["summary"], "promoted": len(result["promoted"])})
    return results


# --- CLI entrypoint (EventBridge/cron invokes this) ---------------------------------

def main(argv=None):
    import argparse
    import os
    p = argparse.ArgumentParser(description="Vault runner — one promotion pass over a tenant's seats.")
    p.add_argument("--now-ts", default=os.environ.get("VAULT_NOW_TS", "2026-01-01T00:00:00Z"),
                   help="Injected ISO timestamp for VL-5 arming (scheduling supplies the tick time).")
    args = p.parse_args(argv)
    palace_id = (os.environ.get("PALACE_ID") or "").strip()
    if not palace_id:
        raise SystemExit("PALACE_ID is required (the tenant/palaceId to run the vault pass for)")
    seats = [s.strip() for s in (os.environ.get("VAULT_SEATS") or os.environ.get("FIDELITY_SEATS") or "").split(",") if s.strip()]
    if not seats:
        raise SystemExit("VAULT_SEATS (or FIDELITY_SEATS) is required (comma-separated seat/neopId list)")
    import json
    for row in run_vault_pass(palace_id, seats, now_ts=args.now_ts):
        print(json.dumps(row, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
