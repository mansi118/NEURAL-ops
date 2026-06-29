"""Unit tests for the SafetyPolicy matrix (T5 — the pure policy core, no jcode/Docker dependency)."""
import pytest

from neop_jcode_adapter.safety_policy import (
    SAFETY_MATRIX, SURFACES, Tier, render_tiers)


def test_every_class_covers_every_surface():
    # no silent surfaces (§6): each class resolves to a complete, explicit policy.
    for cls, tiers in SAFETY_MATRIX.items():
        assert set(tiers) == set(SURFACES), f"class {cls} surface mismatch"


def test_render_tiers_returns_complete_map():
    tiers = render_tiers("B")
    assert set(tiers) == set(SURFACES)


def test_render_tiers_is_case_insensitive():
    assert render_tiers("a") == render_tiers("A")


def test_unknown_class_raises():
    with pytest.raises(ValueError):
        render_tiers("Z")


def test_render_tiers_returns_a_copy():
    # mutating the returned map must not corrupt the shared matrix.
    t = render_tiers("B")
    t["palace"] = Tier.ALWAYS_DENY
    assert SAFETY_MATRIX["B"]["palace"] == Tier.AUTO_ALLOW


def test_class_b_and_c_share_worker_posture():
    assert render_tiers("B") == render_tiers("C")


def test_class_a_is_the_loose_lab_posture():
    a = render_tiers("A")
    assert a["shell_host"] == Tier.SANDBOX_ONLY      # live bash, but only inside the jail
    assert a["self_dev"] == Tier.SANDBOX_ONLY        # self-modify only in a throwaway sandbox
    assert a["swarm_spawn"] == Tier.AUTO_ALLOW
    assert a["browser"] == Tier.ALWAYS_DENY
    assert a["palace"] == Tier.AUTO_ALLOW


def test_worker_denies_shell_and_self_dev():
    for cls in ("B", "C"):
        t = render_tiers(cls)
        assert t["shell_host"] == Tier.ALWAYS_DENY
        assert t["self_dev"] == Tier.ALWAYS_DENY
        assert t["palace"] == Tier.AUTO_ALLOW         # memory is always allowed (shim enforces scope)
        assert t["swarm_spawn"] == Tier.PERMISSION_REQUIRED  # the dynamic tier (hook decides)
