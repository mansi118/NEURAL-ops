"""pre_tool_hook — the jcode ``[hooks].pre_tool`` gate that implements the dynamic ask/allow tier (T5).

jcode runs this executable before every tool call (contract traced from 1jehuang/jcode@master,
``crates/jcode-base/src/hooks.rs`` + ``crates/jcode-app-core/src/tool/mod.rs``):

  * the resolved tool name arrives in env ``JCODE_HOOK_TOOL_NAME`` (e.g. ``bash`` / ``browser`` /
    ``swarm`` / ``mcp__<server>__<tool>`` — aliases are normalised away before we see it);
  * the tool's params JSON is on stdin (and a 16 KB-truncated copy in ``JCODE_HOOK_TOOL_INPUT``);
  * **exit 0 = allow, exit 2 = block** (our stderr becomes the reason shown to the model).
    Any OTHER exit code, a timeout (default 5 s), a spawn failure, or a crash makes jcode **FAIL OPEN**
    (the tool proceeds). That is the sharp edge: this gate alone is NOT a hard boundary — the container
    jail (IsolationUnit, T2) remains the real isolation. So this hook is fail-closed *within its own
    logic* for the governed dangerous surfaces (unknown class / unreadable policy ⇒ deny), and we never
    rely on it as the sole control.

WHY a hook at all: jcode's static ``[tools].disabled`` (rendered by config_render from the safety
matrix) cannot express "allow swarm for Class B but not Class C" — there is no native per-tool ask
tier. This hook is that tier. Its policy is **baked per seat** by config_render into the seat's
container env (``NEOP_SEAT_CLASS`` / ``NEOP_SWARM_ENABLED`` / ``NEOP_JAIL_ENFORCED``) — it is NEVER
taken from the model or the tool params, exactly as the shim bakes (palaceId, neopId).

Run as: ``python3 -m neop_jcode_adapter.pre_tool_hook`` (the command config_render writes into
``[hooks].pre_tool``).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

from .config_render import MCP_SERVER_NAME
from .palace_mcp_shim import ALLOWED_TOOLS_BASE, GATED_TOOLS
from .safety_policy import SAFETY_MATRIX, Tier, render_tiers

# Baked-per-seat env var names (set by config_render.hook_env, injected into the seat container).
ENV_SEAT_CLASS = "NEOP_SEAT_CLASS"
ENV_SWARM_ENABLED = "NEOP_SWARM_ENABLED"
ENV_JAIL_ENFORCED = "NEOP_JAIL_ENFORCED"

# jcode resolved tool name → safety surface (safety_policy.SURFACES). Tools NOT in this map are
# ungoverned in-jail surfaces (read/write/edit/grep/…) — bounded by the container, allowed here.
_TOOL_TO_SURFACE = {
    "bash": "shell_host",
    "browser": "browser",
    "swarm": "swarm_spawn",
    "selfdev": "self_dev",  # jcode registers self-dev as the "selfdev" tool
}

# Palace MCP tools the shim exposes (auto_allow tier); the shim itself is the real scope/allowlist gate.
_PALACE_PREFIX = f"mcp__{MCP_SERVER_NAME}__"
_PALACE_TOOLS = ALLOWED_TOOLS_BASE | GATED_TOOLS

_TRUE = ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str = ""


def decide(tool_name: str, *, seat_class: Optional[str],
           swarm_enabled: bool, jail_enforced: bool) -> Decision:
    """PURE policy: resolve a tool call to allow/deny for a seat. No I/O — unit-testable.

    `seat_class` may be None/unknown (missing baked env) → fail-closed on governed surfaces.
    """
    name = (tool_name or "").strip()

    # ── MCP tools ────────────────────────────────────────────────────────────────
    if name.startswith("mcp__"):
        if name.startswith(_PALACE_PREFIX) and name[len(_PALACE_PREFIX):] in _PALACE_TOOLS:
            return Decision(True)  # palace op (auto_allow) — shim enforces scope + allowlist
        return Decision(False, f"non-palace MCP tool {name!r} denied (only {MCP_SERVER_NAME} palace ops allowed)")
    if name == "mcp":
        return Decision(False, "MCP management tool 'mcp' denied for NEop seats")

    surface = _TOOL_TO_SURFACE.get(name)
    if surface is None:
        # Ungoverned tool (read/write/edit/grep/…): bounded by the container jail, not a safety surface.
        return Decision(True)

    # ── governed dangerous surface — fail-closed if policy is unreadable ──────────
    cls = (seat_class or "").strip().upper()
    if cls not in SAFETY_MATRIX:
        return Decision(False, f"seat class {seat_class!r} unknown/unset — denying governed tool {name!r} (fail-closed)")

    # Class A's loose posture (live bash/swarm/self-dev) is only safe inside an ENFORCED jail; without
    # it, A is a worker — never an unsandboxed dangerous surface. Mirrors config_render.disabled_tools.
    if cls == "A" and not jail_enforced:
        return Decision(False, f"class A sandbox not enforced (jail off) — denying {name!r}")

    tier = render_tiers(cls)[surface]
    if tier == Tier.AUTO_ALLOW:
        return Decision(True)
    if tier == Tier.SANDBOX_ONLY:
        if jail_enforced:
            return Decision(True)
        return Decision(False, f"{name!r} is sandbox-only and the jail is not enforced")
    if tier == Tier.ALWAYS_DENY:
        return Decision(False, f"{name!r} ({surface}) is always denied for class {cls}")
    if tier == Tier.PERMISSION_REQUIRED:
        # The dynamic tier. v1 batch seats have no human ask-UI, so a permission_required surface is
        # allowed ONLY when the seat carries an explicit static grant. The sole grant is swarm_enabled
        # (Class B has it, Class C does not — this is exactly the B/C divergence).
        if surface == "swarm_spawn":
            if swarm_enabled:
                return Decision(True)
            return Decision(False, f"swarm denied: class {cls} seat has no swarm grant")
        return Decision(False, f"{name!r} ({surface}) requires permission and the seat has no grant — denied")
    return Decision(False, f"{name!r}: unhandled tier {tier!r} — denying (fail-closed)")


def main(argv=None) -> int:
    tool = os.environ.get("JCODE_HOOK_TOOL_NAME", "")
    seat_class = os.environ.get(ENV_SEAT_CLASS) or None
    swarm_enabled = (os.environ.get(ENV_SWARM_ENABLED, "") or "").strip().lower() in _TRUE
    jail_enforced = (os.environ.get(ENV_JAIL_ENFORCED, "") or "").strip().lower() in _TRUE
    d = decide(tool, seat_class=seat_class, swarm_enabled=swarm_enabled, jail_enforced=jail_enforced)
    if d.allow:
        return 0
    # exit 2 = block; stderr is fed back to the model as the reason.
    sys.stderr.write(d.reason or "blocked by NEop pre_tool policy")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
