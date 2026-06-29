"""T6 tests for MemoryPromoter — durable jcode export → palace via the shim seam.

DoD (plan §4 T6): durable memory from a session appears in the palace under the right scope; ephemeral
chatter does not. The export only ever contains durable (Project∪Global) entries, so the testable core
is: faithful parse of the real export shape, drop inactive/empty/low-confidence, and write each survivor
through the injected writer (the shim's palace_remember).
"""
import json

import pytest

from neop_jcode_adapter.memory_promoter import (
    MemoryPromoter, PromotableItem, make_shim_writer, normalize_category,
    parse_export, to_palace_remember)


# A reconstructed `jcode memory export --scope all` blob (top-level JSON array of MemoryEntry).
EXPORT = json.dumps([
    {
        "id": "mem_1", "category": "fact", "content": "Convex .site != .cloud",
        "tags": ["infra"], "created_at": "2026-06-18T12:00:00Z", "updated_at": "2026-06-18T12:00:00Z",
        "access_count": 3, "source": "session:abc", "trust": "high", "strength": 2,
        "active": True, "confidence": 1.0,
    },
    {
        "id": "skill:x", "category": {"custom": "Skills"}, "content": "deploy the spine",
        "tags": [], "created_at": "2026-05-01T00:00:00Z", "updated_at": "2026-05-01T00:00:00Z",
        "access_count": 0, "source": None, "trust": "medium", "strength": 1,
        "active": False, "superseded_by": "mem_1", "confidence": 0.62,  # inactive → dropped
    },
    {
        "id": "mem_3", "category": "preference", "content": "   ",  # empty content → dropped
        "tags": [], "created_at": "2026-06-18T12:00:00Z", "updated_at": "2026-06-18T12:00:00Z",
        "access_count": 0, "source": None, "trust": "low", "strength": 0,
        "active": True, "confidence": 0.9,
    },
])


# ── parsing the real export shape ─────────────────────────────────────────────
def test_parse_array_of_entries():
    items = parse_export(EXPORT)
    assert [i.id for i in items] == ["mem_1", "skill:x", "mem_3"]


def test_parse_accepts_decoded_list():
    assert len(parse_export(json.loads(EXPORT))) == 3


def test_parse_rejects_non_array():
    with pytest.raises(ValueError):
        parse_export('{"items": []}')  # wrapper object is NOT the export shape


def test_category_bare_string():
    assert normalize_category("fact") == "fact"


def test_category_custom_externally_tagged():
    # the load-bearing quirk: Custom serializes as {"custom": "<Name>"}, not a bare string.
    assert normalize_category({"custom": "Skills"}) == "Skills"


def test_category_fallback():
    assert normalize_category(None) == "fact"
    assert normalize_category("") == "fact"


def test_absent_fields_are_not_errors():
    # source/superseded_by/embedding may be absent; active defaults true; confidence defaults 1.0
    items = parse_export('[{"id": "m", "content": "x", "category": "fact"}]')
    assert items[0].active is True and items[0].confidence == 1.0 and items[0].source is None


# ── selection: durable-live only ──────────────────────────────────────────────
def test_select_drops_inactive_and_empty():
    p = MemoryPromoter()
    kept = p.select(parse_export(EXPORT))
    assert [i.id for i in kept] == ["mem_1"]  # skill:x inactive, mem_3 empty


def test_min_confidence_filter():
    items = [PromotableItem("a", "hi", "fact", (), True, 0.5, None)]
    assert MemoryPromoter(min_confidence=0.0).select(items) == items
    assert MemoryPromoter(min_confidence=0.8).select(items) == []


def test_to_palace_remember_shape():
    it = PromotableItem("a", "body", "fact", ("t",), True, 1.0, None)
    assert to_palace_remember(it) == {"content": "body", "category": "fact"}


# ── promote(): writes survivors through the injected writer, counts outcomes ───
def test_promote_writes_only_durable_live():
    captured = []

    def writer(params):
        captured.append(params)
        return True

    res = MemoryPromoter().promote(EXPORT, writer)
    assert res.promoted == 1 and res.skipped == 2 and res.failed == 0
    assert captured == [{"content": "Convex .site != .cloud", "category": "fact"}]


def test_promote_counts_writer_failures():
    res = MemoryPromoter().promote(EXPORT, writer=lambda p: False)
    assert res.promoted == 0 and res.failed == 1 and res.skipped == 2


def test_promote_writer_exception_is_failed_not_fatal():
    def boom(params):
        raise RuntimeError("palace down")

    res = MemoryPromoter().promote(EXPORT, boom)  # must not propagate
    assert res.failed == 1 and res.promoted == 0
    assert res.total == 3


def test_load_export_from_file(tmp_path):
    f = tmp_path / "mem.json"
    f.write_text(EXPORT)
    assert [i.id for i in MemoryPromoter.load_export(str(f))] == ["mem_1", "skill:x", "mem_3"]


# ── make_shim_writer: success only on http 200 + status ok ────────────────────
class _FakeShim:
    def __init__(self, out):
        self.out = out
        self.calls = []

    def call(self, name, params):
        self.calls.append((name, params))
        return self.out


def test_shim_writer_success():
    shim = _FakeShim({"http_status": 200, "response": {"status": "ok"}})
    assert make_shim_writer(shim)({"content": "x"}) is True
    assert shim.calls[0][0] == "palace_remember"


def test_shim_writer_failure_on_non_ok():
    assert make_shim_writer(_FakeShim({"http_status": 403, "response": {"status": "denied"}}))({"content": "x"}) is False
    assert make_shim_writer(_FakeShim({"http_status": 200, "response": {"status": "error"}}))({"content": "x"}) is False
