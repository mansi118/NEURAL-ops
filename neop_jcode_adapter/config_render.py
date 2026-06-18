"""ConfigRenderer — per-seat jcode home (config.toml + .jcode/mcp.json + safety policy).

Plan §3.2 / task T2. BLOCKED on the jcode interface trace: the exact config.toml schema, the
mcp.json shape, and the safety-system config dialect must come from the jcode clone
(/mnt/c/Users/LENOVO/Downloads/Jcode), not from the plan's best-guess examples. Once confirmed
(Explore agent / Open Decision §8.1 OpenClaw lineage), render:

  * config.toml      — provider=claude, ANTHROPIC_API_KEY via api_key_env, pinned Claude model id
  * .jcode/mcp.json  — points ONLY at palace_mcp_shim; carries PALACE_MCP_URL / PALACE_ID / NEOP_ID /
                       PALACE_SIGNING_KEY_REF (a keyref, never a plaintext key). jcode never sees the
                       raw palace URL or signing key beyond launching the shim subprocess.
  * safety config    — translate safety_policy.render_tiers(seat_class) into jcode's dialect.

Per-seat JCODE_HOME so config/creds/local-memory-graph never share state across seats.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RenderedSeat:
    jcode_home: str
    config_toml_path: str
    mcp_json_path: str


class ConfigRenderer:
    def render(self, *, palace_id: str, neop_id: str, seat_class: str, jcode_home: str,
               palace_mcp_url: str, signing_key_ref: str, model_id: str) -> RenderedSeat:
        raise NotImplementedError("T2 — pending jcode config schema from the clone")
