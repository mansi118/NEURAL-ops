"""Vault promotion (Flow 4) — decide which candidate memory writes become DURABLE.

A layer OVER the broker's candidate writes (`MemoryBroker.write` records candidates in
`broker.writes`); core.py / dispatch() are untouched. The five gates, in order:

  VL-1  confidence threshold     — per-category minimum bar
  VL-2  PII / secret redaction   — mask values in content (applied, not a reject)
  VL-3  provenance present       — source_adapter, source_external_id, author_*
  VL-4  approval (Decision Queue)— explicit consent; conservative bias -> needs_review
  VL-5  rollback armed           — reversible (30d) + do-not-re-promote marker

Outcomes: promote | hold (low_confidence / needs_review) | reject. Pure + deterministic.
The async "Vault Promoter" cadence (nightly / session-close) is a scheduling concern; this
module is the decision logic it runs. Default posture is conservative: a raw NEop write does
NOT auto-promote — it must clear every gate, so the palace stays clean.
"""
from __future__ import annotations
import re
from datetime import datetime

# VL-1: per-category confidence floors (conservative defaults).
CONFIDENCE_FLOORS = {"decision": 0.6, "fact": 0.5, "lesson": 0.5, "run": 0.7, "_default": 0.5}
PROMOTE_TTL_DAYS = 30

# VL-2: PII / secret patterns -> masked.
_PII = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("card", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("api_key", re.compile(r"\b(?:sk|rk)-[A-Za-z0-9]{16,}\b")),
    ("phone", re.compile(r"\b\+?\d[\d -]{8,}\d\b")),
]
PROV_REQUIRED = ("source_adapter", "source_external_id", "author_type", "author_id")


def redact(text):
    """VL-2: mask PII/secrets in text. Returns (redacted_text, sorted_kinds_found)."""
    if not isinstance(text, str):
        return text, []
    found = []
    for kind, pat in _PII:
        if pat.search(text):
            found.append(kind)
            text = pat.sub(f"[REDACTED:{kind}]", text)
    return text, sorted(set(found))


def promote(record, *, approvals=None, promoted_keys=None, floors=None, now_ts="2026-01-01T00:00:00Z"):
    """Run VL-1..VL-5 on one candidate record. Returns {decision, reason, gates, key, record}."""
    approvals = approvals or {}
    promoted_keys = promoted_keys or set()
    floors = floors or CONFIDENCE_FLOORS
    prov = record.get("provenance", {}) or {}
    key = prov.get("source_external_id") or record.get("dedup_key")
    gates, rec = {}, dict(record)

    if key in promoted_keys:                                    # VL-5 do-not-re-promote
        return {"decision": "reject", "reason": "VL-5 already promoted (do_not_re_promote)",
                "gates": {"VL-5": "blocked"}, "key": key, "record": rec}

    floor = floors.get(record.get("category"), floors.get("_default", 0.5))   # VL-1
    conf = record.get("confidence", 0.0)
    if conf < floor:
        gates["VL-1"] = "fail"
        return {"decision": "hold", "reason": f"VL-1 confidence {conf} < {floor}",
                "gates": gates, "key": key, "record": rec}
    gates["VL-1"] = "pass"

    rec["content"], kinds = redact(rec.get("content"))          # VL-2 (applied)
    rec["pii_redacted"] = kinds
    gates["VL-2"] = f"redacted:{kinds}" if kinds else "clean"

    missing = [k for k in PROV_REQUIRED if not prov.get(k)]     # VL-3
    if missing:
        gates["VL-3"] = "fail"
        return {"decision": "reject", "reason": f"VL-3 provenance missing {missing}",
                "gates": gates, "key": key, "record": rec}
    gates["VL-3"] = "pass"

    verdict = approvals.get(key, record.get("approval"))        # VL-4 (Decision Queue)
    if verdict == "reject":
        gates["VL-4"] = "rejected"
        return {"decision": "reject", "reason": "VL-4 rejected in Decision Queue",
                "gates": gates, "key": key, "record": rec}
    if verdict not in ("promote", "edit", True):               # conservative bias
        gates["VL-4"] = "needs_review"
        return {"decision": "hold", "reason": "VL-4 awaiting approval (Decision Queue)",
                "gates": gates, "key": key, "record": rec}
    gates["VL-4"] = "approved"

    rec["rollback_armed"] = True                                # VL-5
    rec["do_not_re_promote"] = True
    rec["promoted_at"] = now_ts
    rec["rollback_ttl_days"] = PROMOTE_TTL_DAYS
    gates["VL-5"] = "armed"
    return {"decision": "promote", "reason": "all gates passed", "gates": gates,
            "key": key, "record": rec}


def promote_all(records, *, approvals=None, floors=None):
    """Batch over a run's candidate writes (broker.writes). Threads do-not-re-promote."""
    promoted_keys, out = set(), []
    for r in records:
        d = promote(r, approvals=approvals, promoted_keys=promoted_keys, floors=floors)
        if d["decision"] == "promote":
            promoted_keys.add(d["key"])
        out.append(d)
    return out


def _parse_ts(ts):
    """ISO-8601 -> datetime (tolerates a trailing Z). Both timestamps are INJECTED, not wall-clock."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def rollback(record, *, now_ts="2026-01-01T00:00:00Z"):
    """VL-5 reversal — retract a promoted record within its TTL. Returns a tombstone directive.

    This is the other half of VL-5: promote() *arms* a reversible promotion (rollback_armed +
    promoted_at + 30d TTL); rollback() is what actually reverses it. The memory layer applies the
    returned tombstone (retract the durable closet). Reversal CLEARS do_not_re_promote so a
    corrected version can later be re-promoted — the caller drops `key` from its promoted_keys.

    Conservative refuses: won't roll back something never promoted, or past its 30-day window
    (or a record whose promoted_at is in the future relative to now_ts — a clock inconsistency).
    """
    key = (record.get("provenance", {}) or {}).get("source_external_id") or record.get("dedup_key")
    if not record.get("rollback_armed"):
        return {"decision": "reject", "reason": "VL-5 not promoted (nothing to roll back)", "key": key}
    ttl = record.get("rollback_ttl_days", PROMOTE_TTL_DAYS)
    promoted_at = record.get("promoted_at")
    age_days = (_parse_ts(now_ts) - _parse_ts(promoted_at)).days if promoted_at else None
    if age_days is None or not 0 <= age_days <= ttl:
        return {"decision": "reject", "key": key,
                "reason": f"VL-5 rollback window lapsed (age {age_days}d, ttl {ttl}d)"}
    return {"decision": "rollback", "reason": "retracted within TTL", "key": key,
            "tombstone": {"key": key, "retracted_at": now_ts, "reverses_promoted_at": promoted_at},
            "clear_do_not_re_promote": True}
