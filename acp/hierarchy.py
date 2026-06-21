"""Hierarchy Resolver (P4 meta-NEop logic) — the org-chart for delegation + escalation.

Pure + offline. Given a tenant's org-chart (seats, each with a role, a reporting line, and the
capabilities it can handle) the resolver answers two ACP-routing questions:
  - DELEGATION: route a capability DOWN to a subordinate that actually holds it.
  - ESCALATION: route a blocked / over-scope action UP the reporting line.
The ACP Router consumes this; no core.py, no network. Mirrors the conservative, provenance-derived
posture of the other meta-NEops (acp/approval, runtime/curator).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

__all__ = ["Seat", "OrgChart", "HierarchyError", "escalate", "escalation_chain",
           "subordinates", "delegate"]


class HierarchyError(ValueError):
    pass


@dataclass(frozen=True)
class Seat:
    seat_id: str
    role: str                                  # owner | admin | member (or a domain role)
    reports_to: Optional[str] = None           # the seat this one escalates TO (None = top)
    capabilities: frozenset = field(default_factory=frozenset)


@dataclass
class OrgChart:
    seats: dict                                # {seat_id: Seat}

    def __post_init__(self):
        for sid, s in self.seats.items():
            if s.seat_id != sid:
                raise HierarchyError(f"seat key {sid!r} != seat_id {s.seat_id!r}")
            if s.reports_to is not None and s.reports_to not in self.seats:
                raise HierarchyError(f"{sid} reports_to unknown seat {s.reports_to!r}")
        # No cycles in the reporting chain (would loop escalation forever).
        for sid in self.seats:
            seen, cur = set(), sid
            while cur is not None:
                if cur in seen:
                    raise HierarchyError(f"reporting cycle through {cur!r}")
                seen.add(cur)
                cur = self.seats[cur].reports_to

    def get(self, seat_id: str) -> Seat:
        s = self.seats.get(seat_id)
        if s is None:
            raise HierarchyError(f"unknown seat {seat_id!r}")
        return s


def escalate(seat_id: str, org: OrgChart) -> Optional[str]:
    """The single next seat UP the chain (None if already top)."""
    return org.get(seat_id).reports_to


def escalation_chain(seat_id: str, org: OrgChart) -> list:
    """The full chain UP from seat_id (exclusive) to the top. Cycle-safe (validated)."""
    out, cur = [], org.get(seat_id).reports_to
    while cur is not None:
        out.append(cur)
        cur = org.seats[cur].reports_to
    return out


def subordinates(seat_id: str, org: OrgChart) -> list:
    """All seats whose escalation chain passes through seat_id (its whole subtree, sorted)."""
    org.get(seat_id)  # validate
    out = [sid for sid in org.seats if sid != seat_id and seat_id in escalation_chain(sid, org)]
    return sorted(out)


def delegate(capability: str, from_seat: str, org: OrgChart) -> Optional[str]:
    """Route `capability` to a SUBORDINATE that holds it (nearest first by chain depth).
    Returns the chosen seat_id, or None if no subordinate can handle it (→ caller escalates instead)."""
    subs = subordinates(from_seat, org)
    holders = [s for s in subs if capability in org.seats[s].capabilities]
    if not holders:
        return None
    # Nearest = shortest escalation chain back up to from_seat.
    holders.sort(key=lambda s: (escalation_chain(s, org).index(from_seat), s))
    return holders[0]
