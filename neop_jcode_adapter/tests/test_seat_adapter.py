"""SeatAdapter assembly tests — the per-seat glue, offline.

Covers the fail-closed preflight (every prerequisite, collected not short-circuited), the offline
assembly (shim scope-lock + rendered config + validated jail + wired taps + env passthrough), and the
box-gated launch boundary (refuses on failed preflight; the spawn itself raises box-gated).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from neop_jcode_adapter.seat_adapter import (
    SeatSpec, preflight, assemble, launch, PROVIDER_KEY_ENV)
from neop_jcode_adapter.config_render import ANTHROPIC_PROVIDER, OPENROUTER_PROVIDER
from neop_jcode_adapter.audit_tap import AuditTap
from neop_jcode_adapter.event_bridge import EventBridge
from neop_jcode_adapter.supervisor import SeatSupervisor

URL = "https://small-dogfish-433.convex.site/mcp"
PASS = lambda: True
FAIL = lambda: False


def spec(**over):
    base = dict(
        palace_id="pal_test", neop_id="aria", seat_class="C", palace_mcp_url=URL,
        image="neos-jcode:latest", workdir_mount="/var/seats/pal_test/aria",
        jcode_home="/var/seats/pal_test/aria/.jcode", provider=ANTHROPIC_PROVIDER)
    base.update(over)
    return SeatSpec(**base)


def taps(tmp_path):
    return (AuditTap(sink=lambda e: None), EventBridge(sink=lambda s, e: None))


def good_env():
    return {"ANTHROPIC_API_KEY": "sk-xxx", "OPENROUTER_API_KEY": "or-xxx"}


# ---- preflight: the green path requires the box probes to pass ----

def test_preflight_green_with_box_probes_passing():
    r = preflight(spec(), env=good_env(), docker_probe=PASS, jcode_probe=PASS)
    assert r.ok is True and r.failures == []


def test_preflight_collects_all_failures_not_just_first():
    r = preflight(spec(palace_id="", neop_id="_admin", palace_mcp_url="", image=""),
                  env={}, docker_probe=FAIL, jcode_probe=FAIL)
    assert r.ok is False
    blob = " | ".join(r.failures)
    assert "PALACE_ID is blank" in blob
    assert "_admin" in blob                       # reserved identity
    assert "PALACE_MCP_URL is blank" in blob
    assert "image is blank" in blob
    assert "model key env ANTHROPIC_API_KEY is unset" in blob
    assert "Docker daemon not reachable" in blob
    assert "jcode binary not found" in blob


def test_preflight_fails_on_reserved_seat():
    r = preflight(spec(neop_id="_system"), env=good_env(), docker_probe=PASS, jcode_probe=PASS)
    assert r.ok is False and any("_system" in f for f in r.failures)


def test_preflight_fails_on_missing_model_key():
    r = preflight(spec(), env={}, docker_probe=PASS, jcode_probe=PASS)
    assert r.ok is False and any("ANTHROPIC_API_KEY" in f for f in r.failures)


def test_preflight_openrouter_checks_its_own_key_env():
    r = preflight(spec(provider=OPENROUTER_PROVIDER), env={"OPENROUTER_API_KEY": "or-x"},
                  docker_probe=PASS, jcode_probe=PASS)
    assert r.ok is True


def test_preflight_unknown_provider_fails():
    r = preflight(spec(provider="evil"), env=good_env(), docker_probe=PASS, jcode_probe=PASS)
    assert r.ok is False and any("unknown provider" in f for f in r.failures)


def test_preflight_unknown_seat_class_fails():
    r = preflight(spec(seat_class="Z"), env=good_env(), docker_probe=PASS, jcode_probe=PASS)
    assert r.ok is False and any("unknown seat_class" in f for f in r.failures)


def test_preflight_class_a_without_jail_warns_not_fails():
    r = preflight(spec(seat_class="A"), env=good_env(), docker_probe=PASS, jcode_probe=PASS)
    assert r.ok is True
    assert any("Class A without jail_enforced" in w for w in r.warnings)


def test_preflight_box_probes_real_default_fail_here():
    """No injected probes → the real probes run; this dev box has no reachable Docker/jcode, so honest."""
    r = preflight(spec(), env=good_env())
    assert r.ok is False
    assert any("Docker" in f or "jcode" in f for f in r.failures)


def test_preflight_unsigned_warns():
    r = preflight(spec(), env=good_env(), docker_probe=PASS, jcode_probe=PASS)
    assert any("unsigned" in w for w in r.warnings)


# ---- assemble: offline, fail-closed sub-builds ----

def test_assemble_wires_all_parts():
    a, e = taps(None)
    asm = assemble(spec(), audit=a, events=e, write=False)
    assert asm.seat == ("pal_test", "aria")
    # shim baked the scope from spec, never the model
    body, _ = asm.shim.build_request("palace_search", {"query": "x"})
    assert (body["palaceId"], body["neopId"]) == ("pal_test", "aria")
    # jail: exactly one host bind == the workdir; egress is palace + model host only
    binds = [asm.jail_spec.docker_args[i + 1] for i, x in enumerate(asm.jail_spec.docker_args) if x == "-v"]
    assert binds == ["/var/seats/pal_test/aria:/work"]
    assert set(asm.jail_spec.egress_allowlist) == {"api.anthropic.com", "small-dogfish-433.convex.site"}


def test_assemble_passes_through_key_and_policy_env_names_only():
    a, e = taps(None)
    asm = assemble(spec(), audit=a, events=e, write=False)
    # the model key + the hook policy vars are forwarded by NAME; no value (no "=") leaks onto the arg line
    assert "ANTHROPIC_API_KEY" in asm.env_passthrough
    assert "NEOP_SEAT_CLASS" in asm.env_passthrough
    assert all("=" not in n for n in asm.env_passthrough)
    # the policy VALUES are computed for the launcher to set in env, baked per-seat (never from model)
    assert asm.hook_env["NEOP_SEAT_CLASS"] == "C"
    assert asm.hook_env["NEOP_SWARM_ENABLED"] == "0"     # Class C: no swarm grant


def test_assemble_class_b_grants_swarm_in_policy():
    a, e = taps(None)
    asm = assemble(spec(seat_class="B"), audit=a, events=e, write=False)
    assert asm.hook_env["NEOP_SWARM_ENABLED"] == "1"     # Class B: swarm grant (hook gates it)


def test_assemble_forwards_env_signing_key_name(monkeypatch):
    # a valid base64 32-byte Ed25519 seed so the shim's signer resolves (signing is forward-looking)
    monkeypatch.setenv("PALACE_SIGNING_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    a, e = taps(None)
    asm = assemble(spec(signing_key_ref="env:PALACE_SIGNING_KEY"), audit=a, events=e, write=False)
    assert "PALACE_SIGNING_KEY" in asm.env_passthrough


def test_assemble_refuses_reserved_seat():
    a, e = taps(None)
    with pytest.raises(Exception):
        assemble(spec(neop_id="_admin"), audit=a, events=e, write=False)


def test_assemble_refuses_sensitive_workdir_mount():
    a, e = taps(None)
    with pytest.raises(ValueError):
        assemble(spec(workdir_mount="/var/run/docker.sock"), audit=a, events=e, write=False)


def test_assemble_writes_config_files(tmp_path):
    a, e = taps(None)
    home = str(tmp_path / "jhome")
    asm = assemble(spec(jcode_home=home), audit=a, events=e, write=True)
    assert os.path.exists(asm.rendered.config_toml_path)
    assert os.path.exists(asm.rendered.mcp_json_path)
    assert "cortex-palace" in asm.rendered.mcp_json     # the per-seat MCP server is wired


def test_assemble_audit_callable_is_the_tap():
    rows = []
    a = AuditTap(sink=rows.append)
    e = EventBridge(sink=lambda s, ev: None)
    asm = assemble(spec(), audit=a, events=e, write=False)
    with pytest.raises(Exception):
        asm.shim.call("palace_delete", {"query": "x"})   # denied tool
    assert rows and rows[0]["result"] == "deny"           # the assembled shim audits through the tap


# ---- launch: box-gated boundary ----

def test_launch_refuses_on_failed_preflight():
    a, e = taps(None)
    asm = assemble(spec(), audit=a, events=e, write=False)
    with pytest.raises(RuntimeError, match="preflight failed"):
        launch(asm, SeatSupervisor(), env={})            # no key, no box -> preflight fails


def test_launch_box_gated_spawn_raises_after_preflight_passes():
    """With preflight skipped (the box would pass it), the spawn itself is the box-gated boundary."""
    events = []
    a = AuditTap(sink=lambda x: None)
    e = EventBridge(sink=lambda s, ev: events.append((s, ev)))
    asm = assemble(spec(), audit=a, events=e, write=False)
    with pytest.raises(NotImplementedError):
        launch(asm, SeatSupervisor(), skip_preflight=True)
    # the `started` lifecycle event fired BEFORE the box-gated spawn (leaves a trail)
    assert any(s == "neop.lifecycle.started" for s, _ in events)


def test_provider_key_env_map_is_complete():
    assert PROVIDER_KEY_ENV[ANTHROPIC_PROVIDER] == "ANTHROPIC_API_KEY"
    assert PROVIDER_KEY_ENV[OPENROUTER_PROVIDER] == "OPENROUTER_API_KEY"
