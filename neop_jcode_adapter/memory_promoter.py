"""MemoryPromoter — session-end promotion of jcode's durable memory → palace (plan §3.7 / T6).

jcode's memory graph is DURABLE (corrects §3.7's "ephemeral"): it persists at ``$JCODE_HOME/memory/``
with Project + Global scopes (both durable) — there is NO durable Session scope; per-turn chatter is
in-memory only and never reaches disk. So "promote durable, drop ephemeral" is satisfied *by the export
itself*: ``jcode memory export <out> --scope all`` writes only the durable Project ∪ Global entries.

EXPORT FORMAT (traced from jcode@master ``jcode-memory-types`` + ``cli/commands.rs`` — a sandboxed read):
a single pretty-printed **JSON array of MemoryEntry objects** (NOT NDJSON, no wrapper, no edges/tags-
as-nodes — edges live only in the on-disk MemoryGraph, which export drops). Per-entry fields are verbatim
snake_case. Load-bearing quirks this parser handles:
  * ``category`` is a bare lowercase string ("fact"/"preference"/"entity"/"correction") OR, for custom
    categories, the externally-tagged object ``{"custom": "<Name>"}``.
  * the export INCLUDES superseded/inactive entries (``active: false``) — we drop them (promote live only).
  * ``source``/``embedding``/``superseded_by`` may be null/absent — absence is normal, not an error.

Promotion writes each selected entry into the palace via ``palace_remember`` THROUGH THE SHIM (scope
baked + audited), NEVER a direct palace call. To keep this module pure + offline-testable, the actual
write is an injected ``writer`` callable; ``make_shim_writer(shim)`` wraps a live PalaceShim in prod.
The palace stays SoT; the jcode graph is the per-seat working cache (mirrors the Vault Promoter pattern).

NOTE: ``palace_remember`` accepts only {content, category, wingName?} — jcode ``tags`` and graph edges
have no destination field, so they are NOT carried across (faithful to the narrower palace contract).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, List, Optional, Union


@dataclass(frozen=True)
class PromotableItem:
    """The subset of a jcode MemoryEntry that maps onto palace_remember."""
    id: str
    content: str
    category: str
    tags: tuple
    active: bool
    confidence: float
    source: Optional[str]


@dataclass(frozen=True)
class PromotionResult:
    promoted: int = 0
    skipped: int = 0   # durable export entry filtered out (inactive / empty / below confidence)
    failed: int = 0    # writer rejected/raised (palace refusal or transport error)

    @property
    def total(self) -> int:
        return self.promoted + self.skipped + self.failed


def normalize_category(cat) -> str:
    """jcode MemoryCategory → a palace category string. Handles the bare-string variants and the
    externally-tagged ``{"custom": "<Name>"}`` form; anything unexpected falls back to 'fact'."""
    if isinstance(cat, str):
        return cat or "fact"
    if isinstance(cat, dict):
        if "custom" in cat:
            return str(cat["custom"]) or "fact"
        # unknown externally-tagged shape — take the single value if present
        for v in cat.values():
            return str(v) or "fact"
    return "fact"


def parse_export(data: Union[str, list]) -> List[PromotableItem]:
    """Parse a ``jcode memory export`` blob (JSON string or already-decoded list) into items.
    Raises ValueError on a shape that is not the documented top-level JSON array."""
    items = json.loads(data) if isinstance(data, str) else data
    if not isinstance(items, list):
        raise ValueError("jcode memory export must be a top-level JSON array of MemoryEntry objects")
    out: List[PromotableItem] = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError(f"export entry is not an object: {type(raw).__name__}")
        out.append(PromotableItem(
            id=str(raw.get("id", "")),
            content=str(raw.get("content", "")),
            category=normalize_category(raw.get("category", "fact")),
            tags=tuple(raw.get("tags") or []),
            active=bool(raw.get("active", True)),  # field defaults true in jcode (default_active)
            confidence=float(raw.get("confidence", 1.0)),
            source=raw.get("source"),
        ))
    return out


def to_palace_remember(item: PromotableItem) -> dict:
    """Map a promotable item onto palace_remember params (content required; category passed through)."""
    return {"content": item.content, "category": item.category}


class MemoryPromoter:
    """Promote durable jcode memory into the palace at session end. Pure selection + an injected writer.

    `min_confidence` lets a caller suppress low-confidence (decayed) memories; default 0.0 = promote all
    live entries. Selection drops: inactive/superseded entries, empty content, and below-threshold ones.
    """

    def __init__(self, *, min_confidence: float = 0.0):
        self.min_confidence = min_confidence

    def is_promotable(self, item: PromotableItem) -> bool:
        return (item.active
                and bool(item.content.strip())
                and item.confidence >= self.min_confidence)

    def select(self, items: List[PromotableItem]) -> List[PromotableItem]:
        return [it for it in items if self.is_promotable(it)]

    def promote(self, export_data: Union[str, list],
                writer: Callable[[dict], bool]) -> PromotionResult:
        """Promote every durable, live entry via `writer` (the shim's palace_remember seam).

        `writer(params) -> bool`: True = stored, False = refused. A writer that RAISES counts as failed
        (one bad item never aborts the batch — promotion is best-effort at session end, like audit)."""
        items = parse_export(export_data)
        promoted = skipped = failed = 0
        for it in items:
            if not self.is_promotable(it):
                skipped += 1
                continue
            try:
                ok = writer(to_palace_remember(it))
            except Exception:  # noqa: BLE001 — a single write failure must not lose the rest
                ok = False
            if ok:
                promoted += 1
            else:
                failed += 1
        return PromotionResult(promoted=promoted, skipped=skipped, failed=failed)

    @staticmethod
    def load_export(path: str) -> List[PromotableItem]:
        with open(path, "r", encoding="utf-8") as fh:
            return parse_export(fh.read())


def make_shim_writer(shim) -> Callable[[dict], bool]:
    """Adapt a live PalaceShim into a `writer` for promote(): calls palace_remember through the shim
    (scope baked + audited) and reports success. The shim raises on allowlist/scope violations and
    returns a non-ok http/result status on palace refusals — both surface as a False (failed) here."""
    def writer(params: dict) -> bool:
        out = shim.call("palace_remember", params)
        resp = out.get("response") if isinstance(out, dict) else None
        rstatus = resp.get("status") if isinstance(resp, dict) else None
        return out.get("http_status") == 200 and rstatus == "ok"
    return writer
