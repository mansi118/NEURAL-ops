"""Automation flywheel (Flow 8) — observe -> surface -> approve -> NEop.

A pure decision layer OVER a corpus of finished run results (the `_result()` shape from
core.py: state / phases / events). core.py / dispatch() are untouched. It closes the
product loop: recurring work that humans keep routing by hand becomes a *proposed* catalog
NEop — proposed, never auto-spawned. The five gates, in order:

  FW-1  recurrence floor      — a work-shape must recur >= MIN_OCCURRENCES (enough evidence)
  FW-2  success bias          — only learn from shapes that mostly reach DONE (don't
                                automate a path that fails)
  FW-3  novelty               — don't propose a NEop whose signature already exists in the
                                catalog (no redundant agents)
  FW-4  approval (Decision Queue) — explicit consent; conservative bias -> needs_review
  FW-5  materialize SPEC, not agent — emits a `new_neop.py` scaffold spec for a human to run,
                                + a do-not-re-surface marker. No process auto-creates agents.

Outcomes: surface (then materialize | hold | reject) | hold (low evidence). Pure +
deterministic: no wall-clock, candidates sorted by signature, ties broken stably. The async
"flywheel" cadence (nightly over the run log) is a scheduling concern; this is the logic.
"""
from __future__ import annotations

MIN_OCCURRENCES = 3        # FW-1: evidence floor
SUCCESS_FLOOR = 0.6        # FW-2: 2-in-3 success is worth automating; a coin-flip (0.5) is not

# FW: reverse of core.PHASE_SETS — infer a role_family from the phases the runs actually ran.
_ROLE_BY_PHASES = {
    ("plan", "execute", "verify"): "meta",
    ("execute", "verify"): "reactive",
    ("execute",): "executor",
}


def signature(seat, tools):
    """A work-shape key: who ran it + the ordered tool spine. Stable, content-derived."""
    return f"{seat}|{','.join(tools)}"


def observe(run, *, seat):
    """Reduce one finished run result to a flywheel signal (the routed NEop = seat)."""
    tools = [e["tool"] for e in run.get("events", []) if e.get("event") == "tool_call"]
    phases = tuple(run.get("phases", []))
    return {"seat": seat, "state": run.get("state"), "tools": tools, "phases": phases,
            "signature": signature(seat, tools)}


def _propose(sig, obs):
    """Build the scaffold spec for a surfaced shape (consumed by tools/new_neop.py)."""
    seat = obs[0]["seat"]
    tools = obs[0]["tools"]
    role = _ROLE_BY_PHASES.get(obs[0]["phases"], "meta")
    neop_id = f"{seat}-auto"
    return {"neop_id": neop_id, "role": role, "tools": tools,
            "scaffold_cmd": f"python3 tools/new_neop.py {neop_id} --role {role} "
                            f"--tools {','.join(tools) or neop_id + '_tool'}"}


def surface(runs, *, existing=(), min_occurrences=MIN_OCCURRENCES, success_floor=SUCCESS_FLOOR):
    """FW-1..FW-3 over a corpus of (run, seat) observations. Returns candidates, sorted by signature.

    `runs` is an iterable of already-observed signals (see observe). `existing` is the catalog
    of seats already present (FW-3 novelty). Each candidate carries its gates + a surface/hold
    decision; held shapes are returned too (so the cadence can log what it declined, never silently).
    """
    groups = {}
    for o in runs:
        groups.setdefault(o["signature"], []).append(o)

    out = []
    for sig in sorted(groups):
        obs = groups[sig]
        n = len(obs)
        ok = sum(1 for o in obs if o["state"] == "DONE")
        rate = round(ok / n, 3)
        seat = obs[0]["seat"]
        gates = {}

        if n < min_occurrences:                                   # FW-1
            gates["FW-1"] = "fail"
            out.append({"decision": "hold", "reason": f"FW-1 {n} occurrences < {min_occurrences}",
                        "signature": sig, "occurrences": n, "success_rate": rate, "gates": gates})
            continue
        gates["FW-1"] = "pass"

        if rate < success_floor:                                  # FW-2
            gates["FW-2"] = "fail"
            out.append({"decision": "hold", "reason": f"FW-2 success {rate} < {success_floor}",
                        "signature": sig, "occurrences": n, "success_rate": rate, "gates": gates})
            continue
        gates["FW-2"] = "pass"

        if seat in set(existing):                                 # FW-3 novelty
            gates["FW-3"] = "fail"
            out.append({"decision": "hold", "reason": f"FW-3 '{seat}' already in catalog",
                        "signature": sig, "occurrences": n, "success_rate": rate, "gates": gates})
            continue
        gates["FW-3"] = "pass"

        out.append({"decision": "surface", "reason": "recurring, reliable, novel",
                    "signature": sig, "occurrences": n, "success_rate": rate,
                    "gates": gates, "proposal": _propose(sig, obs)})
    return out


def triage(candidate, *, approval=None, surfaced_keys=None):
    """FW-4 + FW-5 on a surfaced candidate. Returns {decision, reason, gates, spec?}.

    Conservative bias: no approval -> hold (needs_review). 'reject' drops it. 'approve' emits
    the scaffold spec for a human to run — nothing here spawns an agent. A signature already
    surfaced (`surfaced_keys`) is refused (FW-5 do-not-re-surface), so the queue can't thrash.
    """
    sig = candidate["signature"]
    gates = dict(candidate.get("gates", {}))
    surfaced_keys = surfaced_keys or set()

    if sig in surfaced_keys:                                      # FW-5 do-not-re-surface
        gates["FW-5"] = "blocked"
        return {"decision": "reject", "reason": "FW-5 already surfaced (do_not_re_surface)",
                "signature": sig, "gates": gates}

    if approval == "reject":                                      # FW-4 explicit reject
        gates["FW-4"] = "rejected"
        return {"decision": "reject", "reason": "FW-4 rejected in Decision Queue",
                "signature": sig, "gates": gates}
    if approval not in ("approve", "promote", True):             # conservative bias
        gates["FW-4"] = "needs_review"
        return {"decision": "hold", "reason": "FW-4 awaiting approval (Decision Queue)",
                "signature": sig, "gates": gates}
    gates["FW-4"] = "approved"

    gates["FW-5"] = "spec_only"                                   # FW-5 materialize spec, not agent
    return {"decision": "materialize", "reason": "approved — scaffold spec emitted (run it by hand)",
            "signature": sig, "gates": gates, "spec": candidate["proposal"]}


def run_flywheel(runs, *, existing=(), approvals=None, min_occurrences=MIN_OCCURRENCES,
                 success_floor=SUCCESS_FLOOR):
    """Full pass: surface candidates, then triage each by its signature's approval verdict.

    `approvals` maps signature -> 'approve'|'reject'. Threads do-not-re-surface across the batch
    so the same shape can't materialize twice. Returns (candidates, triaged) — held shapes kept.
    """
    approvals = approvals or {}
    surfaced_keys, triaged = set(), []
    candidates = surface(runs, existing=existing, min_occurrences=min_occurrences,
                         success_floor=success_floor)
    for c in candidates:
        if c["decision"] != "surface":
            continue
        d = triage(c, approval=approvals.get(c["signature"]), surfaced_keys=surfaced_keys)
        if d["decision"] == "materialize":
            surfaced_keys.add(c["signature"])
        triaged.append(d)
    return candidates, triaged
