"""S0.1 — boot self-check (credential-gated container startup). Offline, stdlib only.

Proves the container REFUSES to start without required creds (never a silent no-op),
runs DEGRADED (warns) when only recommended creds are missing, and that either Convex
env key satisfies the SoT requirement. Run: python3 tests/test_selfcheck.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runtime import selfcheck as sc  # noqa: E402

FULL = {
    "CONVEX_SITE_URL": "https://small-dogfish-433.convex.site",
    "ANTHROPIC_API_KEY": "sk-ant-x",
    "OPENROUTER_API_KEY": "sk-or-x",
    "GRAPHITI_BRIDGE_URL": "http://bridge:8100",
}


def test_empty_env_refuses():
    ok, errors, _ = sc.check({})
    assert not ok, "empty env must refuse"
    blob = " ".join(errors)
    assert "CONVEX_SITE_URL" in blob and "ANTHROPIC_API_KEY" in blob, blob
    print("PASS test_empty_env_refuses")


def test_required_present_passes():
    ok, errors, warnings = sc.check(FULL)
    assert ok and not errors, (errors, warnings)
    assert not warnings, warnings  # full env → no warnings
    print("PASS test_required_present_passes")


def test_missing_required_one_still_refuses():
    env = dict(FULL); env.pop("ANTHROPIC_API_KEY")
    ok, errors, _ = sc.check(env)
    assert not ok and any("ANTHROPIC_API_KEY" in e for e in errors), errors
    print("PASS test_missing_required_one_still_refuses")


def test_degraded_recommended_warns_but_ok():
    env = {"CONVEX_DEPLOYMENT_URL": "https://x.convex.cloud", "ANTHROPIC_API_KEY": "sk-ant-x"}
    ok, errors, warnings = sc.check(env)
    assert ok and not errors, errors                       # required satisfied (alt Convex key)
    assert any("OPENROUTER_API_KEY" in w for w in warnings), warnings   # fallback missing → warn, not fail
    assert any("entity graph" in w for w in warnings), warnings
    print("PASS test_degraded_recommended_warns_but_ok")


def test_blank_value_is_not_present():
    ok, _, _ = sc.check({"CONVEX_SITE_URL": "   ", "ANTHROPIC_API_KEY": "x"})
    assert not ok, "whitespace-only value must not count as present"
    print("PASS test_blank_value_is_not_present")


def test_required_key_follows_configured_primary():
    base = {"CONVEX_SITE_URL": "https://x.convex.site"}
    # Primary = openrouter → OPENROUTER required, ANTHROPIC is now just the (present) fallback.
    ok, errors, _ = sc.check({**base, "CLASSIFIER_PROVIDER": "openrouter"})
    assert not ok and any("OPENROUTER_API_KEY" in e for e in errors), errors
    ok, errors, _ = sc.check({**base, "CLASSIFIER_PROVIDER": "openrouter", "OPENROUTER_API_KEY": "sk-or-x"})
    assert ok and not errors, errors
    # An Anthropic key does NOT satisfy an openrouter primary (fallback ≠ boot substitute).
    ok, _, _ = sc.check({**base, "CLASSIFIER_PROVIDER": "openrouter", "ANTHROPIC_API_KEY": "sk-ant-x"})
    assert not ok, "fallback credential must not satisfy the configured primary at boot"
    print("PASS test_required_key_follows_configured_primary")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
    print("ALL SELF-CHECK TESTS PASS")
