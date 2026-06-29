"""T5 tests for the pre_tool hook — the dynamic ask/allow gate.

DoD (plan §4 T5): a Class B/C seat cannot shell out, self-modify, or hit the browser; the swarm grant
is the only thing that opens the permission-gated surface (B yes, C no); Class A's loose posture is
gated on the jail; and an unreadable policy fails CLOSED on governed surfaces. main() maps the decision
to jcode's exit-code contract (0 allow / 2 block, reason on stderr).
"""
from neop_jcode_adapter import pre_tool_hook as H
from neop_jcode_adapter.config_render import MCP_SERVER_NAME

PALACE = f"mcp__{MCP_SERVER_NAME}__"


def d(tool, cls, *, swarm=False, jail=False):
    return H.decide(tool, seat_class=cls, swarm_enabled=swarm, jail_enforced=jail)


# ── worker (Class B/C) — the dangerous surfaces are all denied ─────────────────
def test_worker_cannot_shell_out():
    for cls in ("B", "C"):
        assert d("bash", cls).allow is False


def test_worker_cannot_self_modify():
    for cls in ("B", "C"):
        assert d("selfdev", cls).allow is False


def test_worker_cannot_browse():
    for cls in ("B", "C"):
        assert d("browser", cls).allow is False


# ── the swarm grant is the B/C divergence ─────────────────────────────────────
def test_class_b_swarm_allowed_with_grant():
    assert d("swarm", "B", swarm=True).allow is True


def test_class_c_swarm_denied_without_grant():
    # Class C carries no swarm grant → denied even though the matrix tier is identical to B.
    assert d("swarm", "C", swarm=False).allow is False


def test_swarm_denied_when_grant_absent_regardless_of_class():
    assert d("swarm", "B", swarm=False).allow is False


# ── palace MCP ops are auto-allowed (the shim is the real scope/allowlist gate) ─
def test_palace_ops_allowed():
    for t in ("palace_search", "palace_remember", "palace_get_closet"):
        assert d(PALACE + t, "B").allow is True


def test_non_palace_mcp_denied():
    assert d(PALACE + "evil_tool", "B").allow is False
    assert d("mcp__other__whatever", "B").allow is False
    assert d("mcp", "B").allow is False  # the MCP management tool


# ── ungoverned in-jail tools (read/write/edit/…) pass — the jail bounds them ───
def test_ungoverned_tools_allowed():
    for t in ("read", "write", "edit", "grep", "glob", "ls"):
        assert d(t, "B").allow is True


# ── Class A: loose posture is gated on the enforced jail ───────────────────────
def test_class_a_denied_without_jail():
    for t in ("bash", "swarm", "selfdev"):
        assert d(t, "A", swarm=True, jail=False).allow is False


def test_class_a_allowed_inside_jail():
    assert d("bash", "A", jail=True).allow is True
    assert d("selfdev", "A", jail=True).allow is True
    assert d("swarm", "A", jail=True).allow is True
    assert d("browser", "A", jail=True).allow is False  # browser is always denied, even for A


# ── fail-closed: unreadable/unknown policy denies governed surfaces ────────────
def test_unknown_class_denies_governed():
    for cls in (None, "", "Z"):
        assert d("bash", cls).allow is False
        assert d("swarm", cls, swarm=True).allow is False


def test_unknown_class_still_allows_ungoverned_and_palace():
    # palace has its own enforcement (the shim); ungoverned tools are jail-bounded.
    assert d("read", None).allow is True
    assert d(PALACE + "palace_search", None).allow is True


# ── main() honours jcode's exit-code contract ─────────────────────────────────
def test_main_allow_exit_zero(monkeypatch, capsys):
    monkeypatch.setenv("JCODE_HOOK_TOOL_NAME", PALACE + "palace_search")
    monkeypatch.setenv("NEOP_SEAT_CLASS", "B")
    monkeypatch.setenv("NEOP_SWARM_ENABLED", "0")
    monkeypatch.setenv("NEOP_JAIL_ENFORCED", "0")
    assert H.main() == 0


def test_main_block_exit_two_with_reason(monkeypatch, capsys):
    monkeypatch.setenv("JCODE_HOOK_TOOL_NAME", "bash")
    monkeypatch.setenv("NEOP_SEAT_CLASS", "B")
    monkeypatch.delenv("NEOP_SWARM_ENABLED", raising=False)
    monkeypatch.delenv("NEOP_JAIL_ENFORCED", raising=False)
    assert H.main() == 2
    assert capsys.readouterr().err.strip()  # a non-empty block reason on stderr


def test_main_swarm_grant_via_env(monkeypatch):
    monkeypatch.setenv("JCODE_HOOK_TOOL_NAME", "swarm")
    monkeypatch.setenv("NEOP_SEAT_CLASS", "B")
    monkeypatch.setenv("NEOP_SWARM_ENABLED", "1")
    monkeypatch.setenv("NEOP_JAIL_ENFORCED", "0")
    assert H.main() == 0
    monkeypatch.setenv("NEOP_SWARM_ENABLED", "0")  # revoke grant → blocked
    assert H.main() == 2


def test_main_missing_policy_fails_closed(monkeypatch):
    # no NEOP_SEAT_CLASS baked → governed tool denied (exit 2), never silently allowed.
    monkeypatch.setenv("JCODE_HOOK_TOOL_NAME", "bash")
    monkeypatch.delenv("NEOP_SEAT_CLASS", raising=False)
    assert H.main() == 2
