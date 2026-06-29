"""T2 tests for ConfigRenderer — built to jcode's real config interface.

Asserts the corrections traced from 1jehuang/jcode@master: provider = "anthropic-api" (direct key,
not OAuth "claude"), separate mcp.json with top-level `servers` + `shared: false`, safety tiers →
[tools].disabled, and NO secret ever written to disk.
"""
import json
import os

import pytest

from neop_jcode_adapter.config_render import ConfigRenderer, DEFAULT_MODEL, SHIM_MODULE

URL = "https://small-dogfish-433.convex.site/mcp"
KEYREF = "env:PALACE_SIGNING_KEY_ARIA"


def r():
    return ConfigRenderer()


# ── provider: direct Anthropic key, not OAuth ─────────────────────────────────
def test_provider_is_anthropic_api_direct_key():
    toml = r().render_config_toml("B")
    assert 'default_provider = "anthropic-api"' in toml  # NOT "claude" (that is OAuth)
    assert f'default_model = "{DEFAULT_MODEL}"' in toml


def test_model_override():
    toml = r().render_config_toml("A", model_id="claude-haiku-4")
    assert 'default_model = "claude-haiku-4"' in toml


# ── safety tiers → [tools].disabled ───────────────────────────────────────────
def test_class_b_disables_bash_browser_swarm():
    assert r().disabled_tools("B") == ["bash", "browser", "swarm"]


def test_b_and_c_identical_until_pre_tool_hook():
    # B/C diverge only on permission-gated swarm, which lives in the T5 hook → same config until then.
    assert r().disabled_tools("B") == r().disabled_tools("C") == ["bash", "browser", "swarm"]


def test_class_a_tight_until_jail_enforced():
    # default: jail not asserted live → render A as a worker, never unsandboxed bash+swarm
    assert r().disabled_tools("A") == ["bash", "browser", "swarm"]


def test_class_a_loosens_only_when_jail_enforced():
    assert r().disabled_tools("A", jail_enforced=True) == ["browser"]
    # and the loosened list flows through to the rendered toml
    toml = r().render_config_toml("A", jail_enforced=True)
    assert 'disabled = ["browser"]' in toml


def test_disabled_renders_into_toml():
    toml = r().render_config_toml("B")
    assert 'disabled = ["bash", "browser", "swarm"]' in toml


def test_pre_tool_hook_optional():
    assert "[hooks]" not in r().render_config_toml("B")
    toml = r().render_config_toml("B", pre_tool_hook="/jail/hooks/gate.sh")
    assert "[hooks]" in toml and 'pre_tool = "/jail/hooks/gate.sh"' in toml


# ── mcp.json shape (real jcode schema) ────────────────────────────────────────
def test_mcp_json_shape():
    doc = json.loads(r().render_mcp_json(
        palace_id="pal", neop_id="aria", palace_mcp_url=URL, signing_key_ref=KEYREF))
    assert set(doc) == {"servers"}  # top-level key is `servers`, not `mcpServers`
    srv = doc["servers"]["cortex-palace"]
    assert srv["command"] == "python"
    assert srv["args"] == ["-m", SHIM_MODULE]
    assert srv["shared"] is False  # per-seat stateful shim, never pooled
    assert srv["env"]["PALACE_ID"] == "pal" and srv["env"]["NEOP_ID"] == "aria"
    assert srv["env"]["PALACE_MCP_URL"] == URL
    assert srv["env"]["PALACE_SIGNING_KEY_REF"] == KEYREF


def test_get_closet_gate_flag():
    base = json.loads(r().render_mcp_json(palace_id="p", neop_id="a", palace_mcp_url=URL, signing_key_ref=KEYREF))
    assert "PALACE_ENABLE_GET_CLOSET" not in base["servers"]["cortex-palace"]["env"]
    on = json.loads(r().render_mcp_json(palace_id="p", neop_id="a", palace_mcp_url=URL,
                                        signing_key_ref=KEYREF, enable_get_closet=True))
    assert on["servers"]["cortex-palace"]["env"]["PALACE_ENABLE_GET_CLOSET"] == "1"


# ── no secrets on disk; the key is a REF, the API key is never rendered ────────
def test_no_plaintext_secret_anywhere():
    rs = r().render(palace_id="p", neop_id="a", seat_class="B", jcode_home="/tmp/unused",
                    palace_mcp_url=URL, signing_key_ref=KEYREF, write=False)
    blob = rs.config_toml + rs.mcp_json
    # the keyref appears (it is a reference); a raw Anthropic key / private key must NOT.
    assert KEYREF in blob
    assert "ANTHROPIC_API_KEY" not in blob  # key arrives via container env, never config
    assert "sk-ant" not in blob and "BEGIN PRIVATE KEY" not in blob


# ── actually writes a usable per-seat JCODE_HOME ──────────────────────────────
def test_render_writes_files(tmp_path):
    home = str(tmp_path / "seat_aria")
    rs = r().render(palace_id="pal", neop_id="aria", seat_class="A", jcode_home=home,
                    palace_mcp_url=URL, signing_key_ref=KEYREF)
    assert os.path.isfile(rs.config_toml_path) and os.path.isfile(rs.mcp_json_path)
    assert rs.config_toml_path == os.path.join(home, "config.toml")
    assert rs.mcp_json_path == os.path.join(home, "mcp.json")
    # round-trips as valid JSON
    json.loads(open(rs.mcp_json_path).read())


def test_config_toml_parses_if_tomllib_available():
    tomllib = pytest.importorskip("tomllib")  # py3.11+
    parsed = tomllib.loads(r().render_config_toml("B"))
    assert parsed["provider"]["default_provider"] == "anthropic-api"
    assert parsed["tools"]["disabled"] == ["bash", "browser", "swarm"]


# ── OpenRouter provider (the model path when no Anthropic key is on hand) ──────
from neop_jcode_adapter.config_render import (  # noqa: E402
    OPENROUTER_PROVIDER, OPENROUTER_DEFAULT_MODEL, OPENROUTER_BASE_URL, OPENROUTER_API_KEY_ENV)


def test_default_provider_unchanged_backward_compat():
    # No provider arg ⇒ still anthropic-api (existing seats render byte-identical).
    assert 'default_provider = "anthropic-api"' in r().render_config_toml("B")


def test_openrouter_provider_block():
    toml = r().render_config_toml("B", provider=OPENROUTER_PROVIDER)
    assert 'default_provider = "openrouter"' in toml
    assert "[providers.openrouter]" in toml
    assert 'type = "openrouter"' in toml
    assert f'base_url = "{OPENROUTER_BASE_URL}"' in toml
    assert f'api_key_env = "{OPENROUTER_API_KEY_ENV}"' in toml
    assert f'default_model = "{OPENROUTER_DEFAULT_MODEL}"' in toml  # provider-prefixed id


def test_openrouter_model_override():
    toml = r().render_config_toml("B", provider=OPENROUTER_PROVIDER, model_id="meta-llama/llama-3.1-70b")
    assert 'default_model = "meta-llama/llama-3.1-70b"' in toml


def test_openrouter_no_raw_secret():
    # api_key_env names WHERE the key lives (a reference) — the key VALUE is never rendered.
    toml = r().render_config_toml("A", provider=OPENROUTER_PROVIDER, jail_enforced=True)
    assert "OPENROUTER_API_KEY" in toml          # the env-var NAME (reference) is expected
    assert "sk-or-" not in toml                  # a real OpenRouter key value must NOT appear


def test_unsupported_provider_raises():
    with pytest.raises(ValueError):
        r().render_config_toml("B", provider="bedrock")


def test_openrouter_parses_if_tomllib_available():
    tomllib = pytest.importorskip("tomllib")
    parsed = tomllib.loads(r().render_config_toml("B", provider=OPENROUTER_PROVIDER))
    assert parsed["provider"]["default_provider"] == "openrouter"
    assert parsed["providers"]["openrouter"]["type"] == "openrouter"
    assert parsed["providers"]["openrouter"]["api_key_env"] == "OPENROUTER_API_KEY"
    assert parsed["providers"]["openrouter"]["base_url"] == OPENROUTER_BASE_URL


# ── T5: pre_tool hook integration (the dynamic swarm tier) ────────────────────
def test_hook_enables_swarm_for_class_b():
    # With the hook live AND the swarm grant, Class B keeps swarm ENABLED so the hook can gate it.
    assert r().disabled_tools("B", hook_active=True, swarm_enabled=True) == ["bash", "browser"]


def test_hook_keeps_swarm_disabled_for_class_c():
    # Class C has no swarm grant → swarm stays disabled even with the hook live.
    assert r().disabled_tools("C", hook_active=True, swarm_enabled=False) == ["bash", "browser", "swarm"]


def test_no_hook_means_swarm_disabled_even_with_grant():
    # Backward compat: without a hook, the grant is inert (no native ask tier) → swarm disabled.
    assert r().disabled_tools("B", swarm_enabled=True) == ["bash", "browser", "swarm"]


def test_render_threads_swarm_enable_into_toml():
    toml = r().render_config_toml("B", pre_tool_hook="python3 -m neop_jcode_adapter.pre_tool_hook",
                                  swarm_enabled=True)
    assert 'disabled = ["bash", "browser"]' in toml  # swarm not disabled
    assert "[hooks]" in toml


def test_pre_tool_command():
    assert r().pre_tool_command() == "python3 -m neop_jcode_adapter.pre_tool_hook"
    assert r().pre_tool_command(python="/jail/venv/bin/python") == \
        "/jail/venv/bin/python -m neop_jcode_adapter.pre_tool_hook"


def test_hook_env_is_baked_policy():
    env = ConfigRenderer.hook_env("b", swarm_enabled=True, jail_enforced=False)
    assert env == {"NEOP_SEAT_CLASS": "B", "NEOP_SWARM_ENABLED": "1", "NEOP_JAIL_ENFORCED": "0"}
    env2 = ConfigRenderer.hook_env("A", swarm_enabled=False, jail_enforced=True)
    assert env2 == {"NEOP_SEAT_CLASS": "A", "NEOP_SWARM_ENABLED": "0", "NEOP_JAIL_ENFORCED": "1"}
