"""Unit tests for the seat-class presets (T5 — pure data; the swarm grant is the B/C divergence)."""
import pytest

from neop_jcode_adapter.safety_policy import SURFACES
from neop_jcode_adapter.seat_classes import (
    SEAT_CLASS_PRESETS, SeatClass, preset_for)


def test_all_classes_have_presets():
    assert set(SEAT_CLASS_PRESETS) == set(SeatClass)


def test_preset_carries_complete_tiers():
    for cls, preset in SEAT_CLASS_PRESETS.items():
        assert set(preset.tiers) == set(SURFACES)
        assert preset.seat_class == cls


def test_class_a_requires_sandbox():
    assert preset_for("A").sandbox_required is True
    assert preset_for("B").sandbox_required is False
    assert preset_for("C").sandbox_required is False


def test_swarm_grant_is_the_b_c_divergence():
    # B carries the swarm grant; C does not — the only thing that separates the worker classes.
    assert preset_for("B").swarm_enabled is True
    assert preset_for("C").swarm_enabled is False


def test_preset_for_accepts_str_and_enum():
    assert preset_for("b") is preset_for(SeatClass.B)


def test_preset_for_rejects_unknown():
    with pytest.raises(ValueError):
        preset_for("Z")
