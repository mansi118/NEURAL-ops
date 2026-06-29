"""`python -m neop_jcode_adapter` CLI tests — the runnable preflight entrypoint.

The preflight command must run anywhere and honestly report not-ready off the box. Exercised both as a
function (spec_from_env / main) and as a real subprocess (the path T0 actually invokes).
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from neop_jcode_adapter.__main__ import spec_from_env, main


def test_spec_from_env_reads_scope_and_flags():
    env = {
        "PALACE_ID": "pal1", "NEOP_ID": "aria", "NEOP_SEAT_CLASS": "B",
        "PALACE_MCP_URL": "https://x.convex.site/mcp", "NEOP_IMAGE": "img",
        "NEOP_WORKDIR": "/var/seats/pal1/aria", "JCODE_HOME": "/var/seats/pal1/aria/.jcode",
        "NEOP_JAIL_ENFORCED": "1",
    }
    spec = spec_from_env(env)
    assert (spec.palace_id, spec.neop_id, spec.seat_class) == ("pal1", "aria", "B")
    assert spec.jail_enforced is True
    assert spec.enable_get_closet is False


def test_preflight_cli_returns_nonzero_when_not_ready(monkeypatch):
    # blank scope + no key + no box -> not ready -> exit 1
    for k in ("PALACE_ID", "NEOP_ID", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    rc = main(["preflight"])
    assert rc == 1


def test_preflight_cli_subprocess_runs_and_reports():
    """Real subprocess (the T0 invocation path). Off the box this exits 1 with a clear NOT READY."""
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.update({"PALACE_ID": "pal1", "NEOP_ID": "aria", "PYTHONPATH": REPO})
    r = subprocess.run([sys.executable, "-m", "neop_jcode_adapter", "preflight"],
                       capture_output=True, text=True, env=env, cwd=REPO)
    assert r.returncode == 1
    assert "NOT READY" in r.stderr
    # the missing prerequisites are named (key + box)
    assert "ANTHROPIC_API_KEY" in r.stderr or "Docker" in r.stderr


def test_cli_requires_a_subcommand():
    import pytest
    with pytest.raises(SystemExit):
        main([])
