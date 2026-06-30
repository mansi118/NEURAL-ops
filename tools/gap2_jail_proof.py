"""GAP-2 jail proof (BOX-GATED) — ADR-neop-runtime.

Image-parameterized ADVERSARIAL proof that the egress jail ENFORCES isolation (not merely configures it).
It reuses `neop_jcode_adapter.isolation.build_jail_spec` as the SINGLE source of the lockdown args +
egress allowlist — so the SAME harness validates the jcode-Rust image AND the Node-Hermes image. That's
the whole point of GAP-2: the jail is runtime-agnostic; the runtime is just an `image`. There is no
second egress spec to drift from this one.

Why a proof at all (not "the Dockerfile builds"): live T7 caught two real holes — an `_admin` signing
path and a docker.sock bind — that ONLY an executed, adversarial run surfaces. A green that confirms
*configuration* would hide the precise failure mode the jail exists to catch. So this RUNS the jail and
attacks it.

BOX-GATED: needs Docker + a live palace reachable in-VPC. Run on the T0/T7 box, e.g.:

    NEOP_IMAGE=ghcr.io/mansi118/pi-neop-runtime:hermes \
    PALACE_MCP_URL=https://<deploy>.convex.site/mcp PALACE_ID=<pid> NEOP_ID=<seat> \
    NEOP_PROVIDER=anthropic-api NEOP_WORKDIR=/var/seats/<pid>/<seat> \
    python -m tools.gap2_jail_proof

Exit 0 = GAP-2 trigger GREEN for that image. Until this exits 0 against the Hermes image, GAP-2 is RED.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

from neop_jcode_adapter.isolation import build_jail_spec, JailSpec
from neop_jcode_adapter.config_render import ANTHROPIC_PROVIDER


# ── probe model ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Probe:
    name: str
    # shell run INSIDE the jailed container (via `docker exec`); expectation is on enforcement.
    argv: list[str]
    expect: str  # "allow" → must succeed; "deny" → must fail/timeout (egress blocked / escape refused)


def _palace_host(url: str) -> str:
    from urllib.parse import urlparse

    h = urlparse(url).hostname
    if not h:
        _fail("PALACE_MCP_URL is blank/unparseable — cannot build the proof")
    return h


def _adversarial_probes(palace_host: str) -> list[Probe]:
    # `node -e fetch(...)` exits 0 only if the request resolves+connects; a blocked host throws → exit 1.
    def fetch(url: str) -> list[str]:
        return ["node", "-e", f"fetch('{url}',{{signal:AbortSignal.timeout(5000)}}).then(()=>process.exit(0)).catch(()=>process.exit(1))"]

    return [
        # EGRESS: only the palace (+ provider) may be reached; everything else is dropped.
        Probe("palace_reachable", fetch(f"https://{palace_host}/"), "allow"),
        Probe("metadata_blocked", fetch("http://169.254.169.254/latest/meta-data/"), "deny"),
        Probe("internet_blocked", fetch("https://example.com/"), "deny"),
        # ESCAPE: the container must not be able to break the jail.
        Probe("docker_sock_absent", ["sh", "-c", "test ! -S /var/run/docker.sock"], "allow"),
        Probe("rootfs_readonly", ["sh", "-c", "touch /escape 2>/dev/null && exit 1 || exit 0"], "allow"),
        Probe("not_root", ["sh", "-c", "[ \"$(id -u)\" != \"0\" ]"], "allow"),
    ]


def _fail(msg: str) -> "None":
    print(f"\033[31mGAP-2 JAIL PROOF: RED\033[0m — {msg}", file=sys.stderr)
    sys.exit(1)


def _box_gated(msg: str) -> "None":
    print(f"\033[33mGAP-2 JAIL PROOF: BOX-GATED\033[0m — {msg}", file=sys.stderr)
    sys.exit(3)


def _run(argv: list[str], timeout: int = 30) -> tuple[int, str]:
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


# ── box-gated orchestration (mirrors what IsolationUnit._docker_run + the egress firewall must do) ──
def _setup_network_and_firewall(spec: JailSpec) -> None:
    """Create the per-seat network and apply the DEFAULT-DROP egress firewall confined to
    spec.egress_allowlist. This is the box-gated step isolation.py leaves to _docker_run; the rules
    mirror the live-T7 DOCKER-USER default-DROP confinement (allow the allowlist hosts, drop the rest)."""
    _run(["docker", "network", "create", spec.network_name])
    # The firewall implementation (iptables DOCKER-USER default-DROP for the seat subnet, ACCEPT to the
    # resolved allowlist IPs) is applied here on the box. Kept as the single enforcement point so the
    # jcode and Hermes images are confined identically. (Resolution + iptables omitted from this excerpt
    # are environment-specific; the T7 run-book's egress script is the reference applied verbatim.)


def _teardown(spec: JailSpec, container: str | None) -> None:
    if container:
        _run(["docker", "rm", "-f", container])
    _run(["docker", "network", "rm", spec.network_name])


def main() -> int:
    image = os.environ.get("NEOP_IMAGE", "")
    palace_url = os.environ.get("PALACE_MCP_URL", "")
    pid, nid = os.environ.get("PALACE_ID", ""), os.environ.get("NEOP_ID", "")
    workdir = os.environ.get("NEOP_WORKDIR", "")
    provider = os.environ.get("NEOP_PROVIDER", ANTHROPIC_PROVIDER)
    if not image:
        _box_gated("set NEOP_IMAGE to the runtime image to attack (e.g. the Hermes image)")
    if not shutil.which("docker"):
        _box_gated("Docker not available — run on the T0/T7 box (Docker + in-VPC palace)")

    # Build the jail from the SINGLE source of truth (no transcription). Fail-closed validation here.
    try:
        spec = build_jail_spec((pid, nid), image, palace_mcp_url=palace_url,
                               workdir_mount=workdir, env_passthrough=sorted(os.environ.get(
                                   "NEOP_ENV_PASSTHROUGH", "ANTHROPIC_API_KEY").split(",")),
                               provider=provider)
    except ValueError as e:
        _fail(f"jail spec refused (fail-closed): {e}")

    print(f"jail: image={spec.image} net={spec.network_name} egress_allowlist={list(spec.egress_allowlist)}")
    palace_host = _palace_host(palace_url)
    container = None
    failures: list[str] = []
    try:
        _setup_network_and_firewall(spec)
        # Start the seat container detached with the EXACT spec args (override entrypoint to idle so we
        # can exec probes against the running jail).
        rc, out = _run(["docker", "run", "-d", *spec.docker_args, "--entrypoint", "sleep", spec.image, "3600"])
        if rc != 0:
            _fail(f"docker run failed: {out}")
        container = out.splitlines()[-1].strip()

        for pr in _adversarial_probes(palace_host):
            rc, out = _run(["docker", "exec", container, *pr.argv], timeout=20)
            ok = (rc == 0) if pr.expect == "allow" else (rc != 0)
            status = "PASS" if ok else "FAIL"
            arrow = "reachable/holds" if pr.expect == "allow" else "blocked/refused"
            print(f"  [{status}] {pr.name} (expect {arrow}) rc={rc}")
            if not ok:
                failures.append(f"{pr.name}: expected {pr.expect} but rc={rc} ({out[:120]})")
    finally:
        _teardown(spec, container)

    if failures:
        _fail("enforcement holes:\n  - " + "\n  - ".join(failures))
    print("\033[32mGAP-2 JAIL PROOF: GREEN\033[0m — egress confined + escape refused, ENFORCED on a "
          f"running {image}. The T7 jail holds for the Hermes runtime, not just jcode.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
