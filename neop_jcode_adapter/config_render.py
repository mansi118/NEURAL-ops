"""ConfigRenderer — per-seat jcode home (config.toml + mcp.json), task T2.

Built to jcode's REAL interface (traced 2026-06-18 from 1jehuang/jcode@master — see the report in
the commit body / memory). Corrections vs the plan's assumed shapes:

  * Config dir = ``$JCODE_HOME`` (default ~/.jcode). File = ``$JCODE_HOME/config.toml``. No --config flag.
  * Provider for a DIRECT Anthropic key (invariant #5, bypasses blocked Bedrock) is
    ``default_provider = "anthropic-api"`` — NOT the plan's ``[providers.claude] type="anthropic"``
    (the bare string ``"claude"`` selects OAuth/subscription). Key arrives via the ``ANTHROPIC_API_KEY``
    env of the jailed container — NEVER written into config (no plaintext secrets).
  * MCP config is a SEPARATE JSON file ``$JCODE_HOME/mcp.json`` with top-level key ``servers`` and a
    per-server ``shared`` flag that DEFAULTS TRUE — we force ``false`` so each seat spawns its own
    stateful shim process (the shim is the per-seat tenant chokepoint).
  * jcode has no four-tier safety *config*. Real per-tool gating = ``[tools].enabled/.disabled`` plus a
    ``[hooks].pre_tool`` external gate (exit 2 = block). We translate the safety matrix into
    ``[tools].disabled``; the dynamic ask/allow tier (palace auto-allow, permission_required) is the
    pre_tool hook, wired in T5. ``sandbox_only`` tools stay enabled because the CONTAINER is the
    sandbox (IsolationUnit, T2) — consistent with "the jail carries isolation while ACL is fail-open".

jcode launches the shim via ``python -m neop_jcode_adapter.palace_mcp_shim`` (stdio MCP). jcode never
holds the raw palace URL or signing key beyond the keyref it passes to the shim subprocess env.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

from .safety_policy import Tier, render_tiers

DEFAULT_MODEL = "claude-opus-4-8"  # valid pinned Anthropic id jcode accepts
SHIM_MODULE = "neop_jcode_adapter.palace_mcp_shim"

# safety surfaces → the concrete jcode built-in tool names whose denial they map to.
# (self_dev has no built-in tool: denial = not running `jcode self-dev` + the container jail blocking
#  access to jcode's own install. palace = MCP, auto-exposed, governed by the pre_tool hook in T5.)
_SURFACE_TO_TOOLS = {
    "shell_host": ("bash",),     # raw shell; host-fs isolation itself is the container's job
    "browser": ("browser",),
    "swarm_spawn": ("swarm",),
}
# v1: there is no native per-tool "ask" tier in shipped config, so permission_required collapses to
# deny (safe default; "no silent tool surfaces", §6) until the pre_tool hook lands in T5.
#
# B/C DIVERGENCE lives in the pre_tool hook, NOT here: Class B (swarm batch worker) and Class C (build)
# render the SAME `[tools].disabled` ([bash, browser, swarm]) because the only thing that separates them
# is permission-GATED swarm — and there's no native ask-tier, so swarm is denied for BOTH until the T5
# pre_tool hook is real. seat_classes.swarm_enabled (B=True, C=False) is the hook's input: once the hook
# exists it allows B's gated swarm and denies C's. Until then B==C in config (B's swarm is BLOCKED).
_DENY_TIERS = frozenset({Tier.ALWAYS_DENY, Tier.PERMISSION_REQUIRED})

# the worker (Class B/C) hard-deny list — also the SAFE rendering of Class A before its jail is live.
_WORKER_DISABLED = ["bash", "browser", "swarm"]


@dataclass
class RenderedSeat:
    jcode_home: str
    config_toml_path: str
    mcp_json_path: str
    config_toml: str
    mcp_json: str
    disabled_tools: List[str] = field(default_factory=list)


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_str_array(items) -> str:
    return "[" + ", ".join(_toml_str(x) for x in items) + "]"


class ConfigRenderer:
    def __init__(self, default_model: str = DEFAULT_MODEL):
        self.default_model = default_model

    def disabled_tools(self, seat_class: str, *, jail_enforced: bool = False) -> List[str]:
        cls = seat_class.upper()
        tiers = render_tiers(cls)
        if cls == "A" and not jail_enforced:
            # Class A's loose posture (live bash+swarm, justified by "the container is the sandbox")
            # ASSUMES an ENFORCED container jail. That jail is box-gated (Docker; built on the target at
            # S0.1). Until the caller asserts jail_enforced=True we render A as a WORKER — never emit an
            # unsandboxed bash+swarm seat. The config and the sandbox it assumes go live in the SAME step.
            return list(_WORKER_DISABLED)
        out = set()
        for surface, tools in _SURFACE_TO_TOOLS.items():
            if tiers[surface] in _DENY_TIERS:
                out.update(tools)
        return sorted(out)

    def render_config_toml(self, seat_class: str, *, model_id: Optional[str] = None,
                           pre_tool_hook: Optional[str] = None, jail_enforced: bool = False) -> str:
        disabled = self.disabled_tools(seat_class, jail_enforced=jail_enforced)
        lines = [
            "# Rendered per-seat by neop_jcode_adapter.config_render — DO NOT hand-edit.",
            "# Secrets are NEVER written here: the anthropic-api provider reads its key from the jailed",
            "# container's environment; the palace signing key is a keyref the shim resolves at runtime.",
            "",
            "[provider]",
            "default_provider = " + _toml_str("anthropic-api"),  # direct API key (NOT OAuth "claude")
            "default_model = " + _toml_str(model_id or self.default_model),
            "",
            "[tools]",
            "disabled = " + _toml_str_array(disabled),
        ]
        if pre_tool_hook:
            # external allow/deny/ask gate (T5): exit 2 blocks the tool call.
            lines += ["", "[hooks]", "pre_tool = " + _toml_str(pre_tool_hook)]
        return "\n".join(lines) + "\n"

    def render_mcp_json(self, *, palace_id: str, neop_id: str, palace_mcp_url: str,
                        signing_key_ref: str, enable_get_closet: bool = False) -> str:
        env = {
            "PALACE_MCP_URL": palace_mcp_url,
            "PALACE_ID": palace_id,
            "NEOP_ID": neop_id,
            "PALACE_SIGNING_KEY_REF": signing_key_ref,  # a keyref, never a plaintext key
        }
        if enable_get_closet:
            env["PALACE_ENABLE_GET_CLOSET"] = "1"
        doc = {
            "servers": {
                "cortex-palace": {
                    "command": "python",
                    "args": ["-m", SHIM_MODULE],
                    "env": env,
                    "shared": False,  # per-seat stateful shim — never pool across seats
                }
            }
        }
        return json.dumps(doc, indent=2, sort_keys=True) + "\n"

    def render(self, *, palace_id: str, neop_id: str, seat_class: str, jcode_home: str,
               palace_mcp_url: str, signing_key_ref: str, model_id: Optional[str] = None,
               pre_tool_hook: Optional[str] = None, enable_get_closet: bool = False,
               jail_enforced: bool = False, write: bool = True) -> RenderedSeat:
        config_toml = self.render_config_toml(
            seat_class, model_id=model_id, pre_tool_hook=pre_tool_hook, jail_enforced=jail_enforced)
        mcp_json = self.render_mcp_json(
            palace_id=palace_id, neop_id=neop_id, palace_mcp_url=palace_mcp_url,
            signing_key_ref=signing_key_ref, enable_get_closet=enable_get_closet,
        )
        config_path = os.path.join(jcode_home, "config.toml")
        mcp_path = os.path.join(jcode_home, "mcp.json")
        if write:
            os.makedirs(jcode_home, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(config_toml)
            with open(mcp_path, "w", encoding="utf-8") as fh:
                fh.write(mcp_json)
        return RenderedSeat(
            jcode_home=jcode_home,
            config_toml_path=config_path,
            mcp_json_path=mcp_path,
            config_toml=config_toml,
            mcp_json=mcp_json,
            disabled_tools=self.disabled_tools(seat_class, jail_enforced=jail_enforced),
        )
