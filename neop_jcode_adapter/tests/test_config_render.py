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
