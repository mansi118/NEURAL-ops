"""Tests for the jail POLICY (offline-buildable part of IsolationUnit). The container boundary carries
isolation while ACL is fail-open, so these assert the spec is maximally locked + fail-closed. The actual
docker exec (_docker_run) is box-gated (T0) and not exercised here."""
import pytest

from neop_jcode_adapter.isolation import (
    IsolationUnit, build_jail_spec, egress_allowlist, JailSpec)
from neop_jcode_adapter.config_render import OPENROUTER_PROVIDER, ANTHROPIC_PROVIDER

URL = "https://small-dogfish-433.convex.site/mcp"
SEAT = ("palace1", "aria")


# ── egress allowlist: ONLY the palace + the model host ────────────────────────
def test_egress_anthropic():
    assert egress_allowlist(URL, ANTHROPIC_PROVIDER) == ["api.anthropic.com", "small-dogfish-433.convex.site"]


def test_egress_openrouter():
    assert egress_allowlist(URL, OPENROUTER_PROVIDER) == ["openrouter.ai", "small-dogfish-433.convex.site"]


def test_egress_failclosed_blank_url():
    with pytest.raises(ValueError):
        egress_allowlist("", ANTHROPIC_PROVIDER)


def test_egress_failclosed_unknown_provider():
    with pytest.raises(ValueError):
        egress_allowlist(URL, "bedrock")


# ── jail spec: maximally locked ───────────────────────────────────────────────
def _spec(provider=OPENROUTER_PROVIDER, env=("OPENROUTER_API_KEY", "PALACE_SIGNING_KEY_REF")):
    return build_jail_spec(SEAT, "neos-jcode:latest", palace_mcp_url=URL,
                           workdir_mount="/var/seats/palace1/aria", env_passthrough=list(env), provider=provider)


def test_spec_is_locked_down():
    args = _spec().docker_args
    j = " ".join(args)
    assert "--read-only" in args
    assert "--cap-drop" in args and "ALL" in args
    assert "--security-opt" in args and "no-new-privileges" in args
    assert "--pids-limit" in args
    assert "--memory" in args and "--cpus" in args
    assert "--tmpfs" in args
    # exactly ONE host bind — the jailed workdir — and nothing else mounted from the host
    assert j.count("-v ") == 1
    assert "/var/seats/palace1/aria:/work" in j


def test_spec_not_default_network():
    spec = _spec()
    assert spec.network_name == "neop-palace1-aria"      # per-seat, NOT the shared default bridge
    assert spec.network_name not in ("bridge", "host", "default")
    assert "--network" in spec.docker_args


def test_spec_egress_embedded():
    spec = _spec(provider=OPENROUTER_PROVIDER)
    assert spec.egress_allowlist == ("openrouter.ai", "small-dogfish-433.convex.site")


def test_env_is_names_only_no_secret_values():
    spec = _spec()
    # forwarded by NAME (-e NAME), so the value lives in the launcher env, never in the spec/disk
    assert "OPENROUTER_API_KEY" in spec.docker_args
    blob = " ".join(spec.docker_args)
    assert "=" not in blob.split("-e ")[-1][:40]   # no `NAME=value` form
    assert "sk-or-" not in blob and "sk-ant" not in blob


def test_failclosed_value_in_env_passthrough():
    with pytest.raises(ValueError):  # a NAME=value would leak a secret onto disk
        build_jail_spec(SEAT, "img", palace_mcp_url=URL, workdir_mount="/w",
                        env_passthrough=["OPENROUTER_API_KEY=sk-or-leak"])


@pytest.mark.parametrize("seat", [("", "aria"), ("p", "  "), ("   ", "")])
def test_failclosed_blank_scope(seat):
    with pytest.raises(ValueError):
        build_jail_spec(seat, "img", palace_mcp_url=URL, workdir_mount="/w", env_passthrough=[])


def test_failclosed_blank_image_and_workdir():
    with pytest.raises(ValueError):
        build_jail_spec(SEAT, "  ", palace_mcp_url=URL, workdir_mount="/w", env_passthrough=[])
    with pytest.raises(ValueError):
        build_jail_spec(SEAT, "img", palace_mcp_url=URL, workdir_mount="", env_passthrough=[])


# ── launch validates the spec BEFORE the box-gated exec ───────────────────────
def test_launch_failcloses_before_box_gate():
    # blank scope must raise ValueError (fail-closed validation), NOT reach the box-gated NotImplementedError
    with pytest.raises(ValueError):
        IsolationUnit().launch(("", ""), "img", {}, "/w", palace_mcp_url=URL)


def test_launch_reaches_box_gate_on_valid_input():
    # a VALID seat builds the spec then hits the box-gated docker exec (proves validation passed)
    with pytest.raises(NotImplementedError):
        IsolationUnit().launch(SEAT, "img", {"OPENROUTER_API_KEY": "x"}, "/w",
                               palace_mcp_url=URL, provider=OPENROUTER_PROVIDER)
