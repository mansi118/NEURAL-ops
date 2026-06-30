"""GAP-2 jail proof (BOX-GATED) — ADR-neop-runtime.

Image-parameterized ADVERSARIAL proof that the egress jail ENFORCES isolation (not merely configures it).
It reuses `neop_jcode_adapter.isolation.build_jail_spec` as the SINGLE source of the lockdown args +
egress allowlist — so the SAME harness validates the jcode-Rust image AND the Node-Hermes image. That's
the whole point of GAP-2: the jail is runtime-agnostic; the runtime is just an `image`. There is no
second egress spec to drift from this one.

Why a proof at all (not "the Dockerfile builds"): live T7 caught two real holes — an `_admin` signing
path and a docker.sock bind — that ONLY an executed, adversarial run surfaces. A green that confirms
*configuration* would hide the precise failure mode the jail exists to catch. So this RUNS the jail and
attacks it. Verified green against pi-neop-runtime:hermes on the box 2026-06-30 (this is the exact
enforcement that run used: the T7 DOCKER-USER default-DROP firewall with the Hermes image swapped in).

BOX-GATED: needs Docker + root (iptables) + a live palace reachable in-VPC. Run on the T0/T7 box, e.g.:

    NEOP_IMAGE=pi-neop-runtime:hermes \
    PALACE_MCP_URL=http://convex.<ns>:3211/mcp PALACE_ID=<pid> NEOP_ID=<seat> \
    NEOP_WORKDIR=/var/seats/<pid>/<seat> python -m tools.gap2_jail_proof

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

# The seat subnet the egress firewall binds to. The per-seat docker network is created WITH this subnet
# so the iptables -s rule can default-DROP it (mirrors the T7 egress script verbatim).
SEAT_SUBNET = os.environ.get("GAP2_SUBNET", "172.30.98.0/24")


@dataclass(frozen=True)
class Probe:
    name: str
    argv: list[str]            # run INSIDE the jailed container via `docker exec`
    expect: str                # "allow" → rc 0; "deny" → rc != 0 (egress blocked / escape refused)


def _fail(msg: str) -> "None":
    print(f"\033[31mGAP-2 JAIL PROOF: RED\033[0m — {msg}", file=sys.stderr)
    sys.exit(1)


def _box_gated(msg: str) -> "None":
    print(f"\033[33mGAP-2 JAIL PROOF: BOX-GATED\033[0m — {msg}", file=sys.stderr)
    sys.exit(3)


def _run(argv: list[str], timeout: int = 30) -> tuple[int, str]:
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


def _palace_ip(palace_url: str) -> str:
    from urllib.parse import urlparse

    host = urlparse(palace_url).hostname
    if not host:
        _fail("PALACE_MCP_URL is blank/unparseable — cannot resolve the egress allow target")
    rc, out = _run(["getent", "hosts", host])
    ip = out.split()[0] if out.split() else ""
    if not ip:
        _fail(f"could not resolve palace host {host!r} (getent) — is the box in-VPC?")
    return ip


def _tcp_probe(host: str, port: int) -> list[str]:
    # node TCP connect: exit 0 on connect, 1 on error/timeout (matches the box-proven probe).
    js = (
        "const net=require('net');const s=net.connect({host:process.argv[1],"
        "port:+process.argv[2],timeout:4000});"
        "s.on('connect',()=>{s.destroy();process.exit(0)});"
        "s.on('error',()=>process.exit(1));s.on('timeout',()=>{s.destroy();process.exit(1)});"
    )
    return ["node", "-e", js, host, str(port)]


def _adversarial_probes(palace_ip: str) -> list[Probe]:
    return [
        # EGRESS: only the palace may be reached; metadata + internet are default-DROP'd.
        Probe("palace_reachable", _tcp_probe(palace_ip, 3211), "allow"),
        Probe("metadata_blocked", _tcp_probe("169.254.169.254", 80), "deny"),
        Probe("internet_blocked", _tcp_probe("1.1.1.1", 443), "deny"),
        # ESCAPE: the container must not be able to break the jail.
        Probe("not_root", ["sh", "-c", '[ "$(id -u)" != "0" ]'], "allow"),
        Probe("rootfs_readonly", ["sh", "-c", "touch /app/escape 2>/dev/null && exit 1 || exit 0"], "allow"),
        Probe("docker_sock_absent", ["sh", "-c", "test ! -S /var/run/docker.sock"], "allow"),
    ]


# ── the egress firewall (the box-gated enforcement isolation.py leaves to _docker_run) ──
# Ported verbatim from the T7 egress mechanism: create the per-seat network with a known subnet, then
# DOCKER-USER default-DROP that subnet and ACCEPT only the palace. -I inserts at the top, so the ACCEPT
# (inserted second) sits ABOVE the DROP → palace allowed, everything else dropped.
def _setup_network_and_firewall(spec: JailSpec, palace_ip: str) -> None:
    _run(["docker", "network", "rm", spec.network_name])
    rc, out = _run(["docker", "network", "create", "--subnet", SEAT_SUBNET, spec.network_name])
    if rc != 0:
        _fail(f"could not create jail network {spec.network_name} ({SEAT_SUBNET}): {out}")
    rc, out = _run(["iptables", "-I", "DOCKER-USER", "-s", SEAT_SUBNET, "-j", "DROP"])
    if rc != 0:
        _fail(f"iptables default-DROP failed (need root + DOCKER-USER chain): {out}")
    _run(["iptables", "-I", "DOCKER-USER", "-s", SEAT_SUBNET, "-d", palace_ip, "-j", "ACCEPT"])


def _teardown(spec: JailSpec, container: str | None, palace_ip: str | None) -> None:
    if container:
        _run(["docker", "rm", "-f", container])
    if palace_ip:
        _run(["iptables", "-D", "DOCKER-USER", "-s", SEAT_SUBNET, "-d", palace_ip, "-j", "ACCEPT"])
        _run(["iptables", "-D", "DOCKER-USER", "-s", SEAT_SUBNET, "-j", "DROP"])
    _run(["docker", "network", "rm", spec.network_name])


def main() -> int:
    image = os.environ.get("NEOP_IMAGE", "")
    palace_url = os.environ.get("PALACE_MCP_URL", "")
    pid, nid = os.environ.get("PALACE_ID", ""), os.environ.get("NEOP_ID", "")
    workdir = os.environ.get("NEOP_WORKDIR", "/var/seats/seat")
    provider = os.environ.get("NEOP_PROVIDER", ANTHROPIC_PROVIDER)
    if not image:
        _box_gated("set NEOP_IMAGE to the runtime image to attack (e.g. pi-neop-runtime:hermes)")
    if not shutil.which("docker"):
        _box_gated("Docker not available — run on the T0/T7 box (Docker + root + in-VPC palace)")

    # Build the jail from the SINGLE source of truth (no transcription). Fail-closed validation here.
    try:
        spec = build_jail_spec(
            (pid, nid), image, palace_mcp_url=palace_url, workdir_mount=workdir,
            env_passthrough=sorted(os.environ.get("NEOP_ENV_PASSTHROUGH", "ANTHROPIC_API_KEY").split(",")),
            provider=provider,
        )
    except ValueError as e:
        _fail(f"jail spec refused (fail-closed): {e}")

    palace_ip = _palace_ip(palace_url)
    print(f"jail: image={spec.image} net={spec.network_name} subnet={SEAT_SUBNET} "
          f"egress_allowlist={list(spec.egress_allowlist)} palace_ip={palace_ip}")
    container = None
    failures: list[str] = []
    try:
        _setup_network_and_firewall(spec, palace_ip)
        # Start the seat container detached with the EXACT spec args (override entrypoint to idle so we
        # can exec probes against the running, jailed container).
        rc, out = _run(["docker", "run", "-d", *spec.docker_args, "--entrypoint", "sleep", spec.image, "3600"])
        if rc != 0:
            _fail(f"docker run failed: {out}")
        container = out.splitlines()[-1].strip()

        for pr in _adversarial_probes(palace_ip):
            rc, out = _run(["docker", "exec", container, *pr.argv], timeout=20)
            ok = (rc == 0) if pr.expect == "allow" else (rc != 0)
            arrow = "reachable/holds" if pr.expect == "allow" else "blocked/refused"
            print(f"  [{'PASS' if ok else 'FAIL'}] {pr.name} (expect {arrow}) rc={rc}")
            if not ok:
                failures.append(f"{pr.name}: expected {pr.expect} but rc={rc} ({out[:120]})")
    finally:
        _teardown(spec, container, palace_ip)

    if failures:
        _fail("enforcement holes:\n  - " + "\n  - ".join(failures))
    print("\033[32mGAP-2 JAIL PROOF: GREEN\033[0m — egress confined + escape refused, ENFORCED on a "
          f"running {image}. The T7 jail holds for the Hermes runtime, not just jcode.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
