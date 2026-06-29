"""T7 red-team — adversarial isolation tests (the OFFLINE-gradeable portion of the pre-client-data gate).

These probe the isolation invariants the way an attacker would, cutting across the shim's scope-lock,
the jail policy, and the env/mount surface. They complement the per-unit tests (test_palace_mcp_shim.py,
test_isolation.py) by asserting the *system* properties: the model can never widen its own scope, a
misconfigured seat can never become a privileged identity, and the jail can never be pointed at a
host escape path. The LIVE half of T7 (does the container actually enforce egress / does the daemon
honor the flags) is box-gated and must be re-run on the T0 box — this file makes that pass mechanical.

CLAUDE.md invariant: scope is (palaceId, neopId), NEVER from the model; missing/privileged scope ⇒
the server defaults to `_admin`, which BYPASSES all ACL. So these are the load-bearing checks while the
4-layer ACL is fail-open (the container jail carries isolation).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from neop_jcode_adapter.palace_mcp_shim import (
    PalaceShim, ScopeNotConfigured, ScopeSpoofRejected, ToolRejected, RESERVED_IDENTITIES)
from neop_jcode_adapter.isolation import build_jail_spec, egress_allowlist
from neop_jcode_adapter.config_render import ANTHROPIC_PROVIDER, OPENROUTER_PROVIDER

PAL = "pal_test"
SEAT = "aria"
URL = "https://small-dogfish-433.convex.site/mcp"
SEAT_TUPLE = (PAL, SEAT)


def shim(**over):
    base = dict(palace_url=URL, palace_id=PAL, neop_id=SEAT)
    base.update(over)
    return PalaceShim(**base)


# ============================================================================
# ATTACK CLASS 1 — scope escalation: the model tries to widen its own scope.
# ============================================================================

@pytest.mark.parametrize("forbidden", ["palaceId", "neopId", "tool", "params"])
def test_model_cannot_set_scope_via_top_level_arg(forbidden):
    """Direct: a top-level scope/envelope key in tool args is rejected loudly (visible to audit)."""
    with pytest.raises(ScopeSpoofRejected):
        shim().build_request("palace_search", {"query": "x", forbidden: "attacker_palace"})


@pytest.mark.parametrize("variant", ["PalaceId", "PALACEID", "NeopId", "Tool", "PARAMS", "palaceid"])
def test_case_variant_scope_keys_are_inert_not_an_escalation(variant):
    """Case-variant scope keys dodge the exact-match forbidden set, BUT scope is read from the top-level
    body (env-baked), and the variant lands harmlessly inside `params` — it can NOT change scope. Prove
    the baked scope is unchanged regardless of what the model smuggled."""
    body, _ = shim().build_request("palace_search", {"query": "x", variant: "attacker_palace"})
    assert body["palaceId"] == PAL and body["neopId"] == SEAT      # scope intact
    assert body["params"][variant] == "attacker_palace"           # smuggled key is inert payload only


def test_nested_scope_key_under_params_is_inert():
    """A scope key nested inside a sub-dict is not top-level, so the forbidden check doesn't fire — and
    it's inert because Palace reads scope from the top-level body only. Assert scope is untouched."""
    body, _ = shim().build_request(
        "palace_search", {"query": "x", "filter": {"palaceId": "attacker", "neopId": "_admin"}})
    assert body["palaceId"] == PAL and body["neopId"] == SEAT


def test_scope_is_always_env_baked_even_when_args_empty_or_none():
    for args in (None, {}, {"query": "x"}):
        body, headers = shim().build_request("palace_search", args)
        assert (body["palaceId"], body["neopId"]) == (PAL, SEAT)
        assert headers["X-Palace-Neop"] == SEAT


# ============================================================================
# ATTACK CLASS 2 — becoming a privileged identity (the `_admin` bypass family).
# ============================================================================

@pytest.mark.parametrize("ident", sorted(RESERVED_IDENTITIES))
def test_seat_cannot_be_a_reserved_privileged_identity(ident):
    """An explicit misconfig NEOP_ID=_admin would otherwise be baked AND signed into every request as a
    signed ACL bypass. Refuse it at construction (fail-closed), not just blank scope."""
    with pytest.raises(ScopeNotConfigured):
        shim(neop_id=ident)
    with pytest.raises(ScopeNotConfigured):
        shim(palace_id=ident)


@pytest.mark.parametrize("ident", ["_admin", " _admin ", "_system"])
def test_reserved_identity_rejected_even_with_padding(ident):
    with pytest.raises(ScopeNotConfigured):
        shim(neop_id=ident)


@pytest.mark.parametrize("bad", ["", "   ", "\t", None])
def test_blank_scope_still_fails_closed(bad):
    """The original missing-scope path (→ server defaults to _admin) stays refused."""
    with pytest.raises(ScopeNotConfigured):
        shim(neop_id=bad)
    with pytest.raises(ScopeNotConfigured):
        shim(palace_id=bad)


# ============================================================================
# ATTACK CLASS 3 — tool allowlist bypass.
# ============================================================================

@pytest.mark.parametrize("tool", [
    "palace_delete", "palace_admin", "palace_get_closet",      # not in base allowlist
    "Palace_Search", "palace_search ", " palace_remember",     # case/whitespace variants of allowed
    "palace_search\n", "palace_search;palace_delete",          # injection-ish
])
def test_only_exact_allowlisted_tools_pass(tool):
    with pytest.raises(ToolRejected):
        shim().build_request(tool, {"query": "x"})


def test_gated_tool_stays_gated_unless_explicitly_enabled():
    with pytest.raises(ToolRejected):
        shim().build_request("palace_get_closet", {"closetId": "c1"})
    body, _ = shim(enable_get_closet=True).build_request("palace_get_closet", {"closetId": "c1"})
    assert body["tool"] == "palace_get_closet"


# ============================================================================
# ATTACK CLASS 4 — jail escape via the single host bind / env / egress.
# ============================================================================

@pytest.mark.parametrize("escape", [
    "/var/run/docker.sock",            # the classic: socket bind = root on host
    "/run/docker.sock",
    "/",                               # whole host FS
    "/etc", "/etc/shadow", "/root", "/proc", "/sys", "/dev",
    "/var/run", "/var/lib/docker",
    "relative/path",                   # non-absolute
    "/work/../etc",                    # traversal
    "/work/./sub",                     # un-normalized (single-dot)
    "/work//sub",                      # un-normalized (double-slash)
])
def test_jail_refuses_sensitive_or_unnormalized_mounts(escape):
    with pytest.raises(ValueError):
        build_jail_spec(SEAT_TUPLE, "img", palace_mcp_url=URL, workdir_mount=escape, env_passthrough=[])


def test_jail_tolerates_a_single_trailing_slash():
    """A lone trailing slash is benign (docker normalizes it) — accepted, not a finding."""
    spec = build_jail_spec(SEAT_TUPLE, "img", palace_mcp_url=URL, workdir_mount="/var/seats/x/", env_passthrough=[])
    assert any(a.startswith("/var/seats/x") for a in spec.docker_args)


def test_jail_allows_a_legit_per_seat_workdir():
    spec = build_jail_spec(SEAT_TUPLE, "img", palace_mcp_url=URL,
                           workdir_mount="/var/seats/pal_test/aria", env_passthrough=["ANTHROPIC_API_KEY"])
    # exactly one host bind, and it's the workdir
    binds = [spec.docker_args[i + 1] for i, a in enumerate(spec.docker_args) if a == "-v"]
    assert binds == ["/var/seats/pal_test/aria:/work"]


@pytest.mark.parametrize("leak", ["ANTHROPIC_API_KEY=sk-secret", "FOO=bar"])
def test_jail_refuses_secret_values_in_env_passthrough(leak):
    """env_passthrough is NAMES only — a NAME=VALUE would write a secret onto the docker arg line."""
    with pytest.raises(ValueError):
        build_jail_spec(SEAT_TUPLE, "img", palace_mcp_url=URL, workdir_mount="/w", env_passthrough=[leak])


def test_egress_allowlist_is_exactly_palace_plus_model_host():
    """The jail may reach ONLY the palace + the model host — nothing else. Any third host = a finding."""
    assert set(egress_allowlist(URL, ANTHROPIC_PROVIDER)) == {"api.anthropic.com", "small-dogfish-433.convex.site"}
    assert set(egress_allowlist(URL, OPENROUTER_PROVIDER)) == {"openrouter.ai", "small-dogfish-433.convex.site"}


@pytest.mark.parametrize("bad_url", ["", "   ", "not a url", "no-scheme-host"])
def test_egress_failclosed_on_unparseable_palace_url(bad_url):
    with pytest.raises(ValueError):
        egress_allowlist(bad_url, ANTHROPIC_PROVIDER)


def test_unknown_provider_fails_closed():
    with pytest.raises(ValueError):
        egress_allowlist(URL, "evil-provider")


# ============================================================================
# ATTACK CLASS 5 — audit cannot be silently bypassed (leak-detector integrity).
# ============================================================================

def test_denied_calls_are_audited_not_silent():
    """While the ACL is honest-caller, the audit stream is the ONLY leak-detector — a denial must emit
    a deny row, never vanish."""
    rows = []
    s = PalaceShim(palace_url=URL, palace_id=PAL, neop_id=SEAT, audit=rows.append)
    with pytest.raises(ToolRejected):
        s.call("palace_delete", {"query": "x"})
    assert len(rows) == 1 and rows[0]["result"] == "deny"
    rows.clear()
    with pytest.raises(ScopeSpoofRejected):
        s.call("palace_search", {"palaceId": "attacker"})
    assert len(rows) == 1 and rows[0]["result"] == "deny"


def test_scope_spoof_audit_records_keys_only_never_values():
    """Audit is metadata-only (7-yr retention) — a spoof row must carry attempted KEYS, never the
    attacker-supplied VALUES (no secret/PII into the audit stream)."""
    rows = []
    s = PalaceShim(palace_url=URL, palace_id=PAL, neop_id=SEAT, audit=rows.append)
    with pytest.raises(ScopeSpoofRejected):
        s.call("palace_search", {"palaceId": "super-secret-target-value"})
    blob = repr(rows[0])
    assert "palaceId" in blob and "super-secret-target-value" not in blob
