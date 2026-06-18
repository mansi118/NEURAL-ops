"""Shared append-only jsonl + timestamp helpers for the pre-S0 audit/event fallback (T4).

Append-only so records can never be rewritten — the audit trail is tamper-evident-ish even before
ClickHouse lands. Timestamps come from an injectable clock so tests are deterministic.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Callable, Iterator


def now_fields(clock: Callable[[], float]) -> dict:
    t = clock()
    return {"ts": t, "ts_iso": datetime.fromtimestamp(t, tz=timezone.utc).isoformat()}


def append_jsonl(path: str, record: dict) -> None:
    """Append one record as a line. Creates parent dirs. Raises (loud) on IO failure — an
    unauditable environment must fail, not silently drop (plan §6: auditable or it doesn't ship)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
        fh.flush()


def read_jsonl(path: str) -> Iterator[dict]:
    """Yield records from a jsonl file (empty if absent). For verification / the Day-90 measurement."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def default_clock() -> float:
    return time.time()
