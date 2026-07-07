"""IsolationUnit — one container per (palaceId, neopId); the tenant boundary while ACL is fail-open.

Plan §3.3. The container boundary CARRIES isolation because the 4-layer ACL is fail-open until S0.3
(CLAUDE.md invariant #3) — so the jail must be **fail-closed and maximally locked**: no host FS, all
caps dropped, read-only rootfs, no new privileges, and egress to **only** the palace + the model host.

WHAT'S OFFLINE-BUILDABLE (here, tested): the jail POLICY — `egress_allowlist()` and `build_jail_spec()`
(the exact `docker run` lockdown flags + the egress allowlist the network layer must enforce), with
fail-closed validation. WHAT'S BOX-GATED (T0, on a box with Docker): `_docker_run` — the actual container
start + the egress firewall/proxy that enforces the allowlist. Splitting them lets the security policy be
VERIFIED offline; only the exec needs the box. DO NOT weaken the spec.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from .config_render import ANTHROPIC_PROVIDER, BEDROCK_PROVIDER, PROVIDER_EGRESS_HOST

SeatId = Tuple[str, str]  # (palaceId, neopId)


@dataclass
class Handle:
    seat: SeatId
    container_id: str


@dataclass(frozen=True)
class JailSpec:
    """The fully-resolved, fail-closed jail for one seat. `docker_args` is the lockdown; `egress_allowlist`
    is the ONLY set of hosts the network layer may permit out; `env_passthrough` names the env VARS to
    forward (values come from the launcher's env at run time — never embedded here, no secret on disk)."""
    seat: SeatId
    image: str
    network_name: str
    egress_allowlist: Tuple[str, ...]
    env_passthrough: Tuple[str, ...]
    docker_args: Tuple[str, ...]
    workdir_mount: str


# Defaults — conservative; a seat gets no more than this without an explicit, reviewed change.
PIDS_LIMIT = 256
MEMORY = "2g"
CPUS = "1.0"
TMPFS = "/tmp:rw,noexec,nosuid,size=256m"
CONTAINER_WORKDIR = "/work"

# The jail's single host bind must be a per-seat working dir — NEVER a sensitive host path. A bind of
# the docker socket = container escape; of `/`, `/etc`, `/proc`, … = host-FS exposure. The workdir is
# the one writable bind (rootfs is read-only), so this is the highest-leverage escape vector to close.
_SENSITIVE_MOUNT_PREFIXES = ("/etc", "/proc", "/sys", "/dev", "/boot", "/root", "/var/run", "/run", "/var/lib")
_SENSITIVE_MOUNT_EXACT = frozenset({"/", "/home", "/usr", "/bin", "/sbin", "/lib", "/var"})


def egress_allowlist(palace_mcp_url: str, provider: str = ANTHROPIC_PROVIDER) -> List[str]:
    """The ONLY hosts the jail permits out: the palace MCP host + the model provider host. Everything
    else is dropped. Fail-closed: a blank/unparseable palace URL or unknown provider raises (a jail with
    no resolvable boundary must never launch).

    Provider vocabulary follows the RUNTIME's provider id (the launcher passes it). For the Hermes runtime
    on the SEALED SPINE (deploy-topology Decision 2) that is `BEDROCK_PROVIDER` (`amazon-bedrock`) — pass it
    explicitly, or the default (`anthropic`) would allow the wrong host and the in-VPC Bedrock call would be
    dropped at the box. The default is left as anthropic to avoid changing existing jcode-path callers."""
    host = urlparse(palace_mcp_url).hostname if palace_mcp_url else None
    if not host:
        raise ValueError("egress_allowlist: blank/unparseable palace_mcp_url — refusing (fail-closed)")
    if provider not in PROVIDER_EGRESS_HOST:
        raise ValueError(f"egress_allowlist: unknown provider {provider!r} — refusing (fail-closed)")
    return sorted({host, PROVIDER_EGRESS_HOST[provider]})


def _reject_sensitive_mount(path: str) -> None:
    """Fail-closed: refuse a host bind that is/contains the docker socket or a system path. A normalized
    absolute path is required (no relative/`..` traversal) so the check can't be sidestepped."""
    import posixpath
    if "docker.sock" in path:
        raise ValueError(f"build_jail_spec: refusing to bind the docker socket {path!r} (container escape)")
    if not path.startswith("/"):
        raise ValueError(f"build_jail_spec: workdir_mount must be an absolute path — got {path!r}")
    norm = posixpath.normpath(path)
    if norm != path.rstrip("/") or ".." in path.split("/"):
        raise ValueError(f"build_jail_spec: workdir_mount must be normalized (no '..'/trailing slash) — got {path!r}")
    if norm in _SENSITIVE_MOUNT_EXACT:
        raise ValueError(f"build_jail_spec: refusing to bind sensitive host path {norm!r}")
    for pref in _SENSITIVE_MOUNT_PREFIXES:
        if norm == pref or norm.startswith(pref + "/"):
            raise ValueError(f"build_jail_spec: refusing to bind under sensitive host path {pref!r} (got {norm!r})")


def build_jail_spec(seat: SeatId, image: str, *, palace_mcp_url: str, workdir_mount: str,
                    env_passthrough: List[str], provider: str = ANTHROPIC_PROVIDER) -> JailSpec:
    """Resolve the fail-closed jail for one seat. Pure + testable — no Docker call. Refuses on any input
    that would weaken isolation (blank scope, blank image, blank workdir, a secret VALUE in env_passthrough)."""
    pid, nid = seat
    if not (pid and pid.strip()) or not (nid and nid.strip()):
        raise ValueError("build_jail_spec: blank palaceId/neopId — refusing (fail-closed scope)")
    if not (image and image.strip()):
        raise ValueError("build_jail_spec: blank image — refusing")
    if not (workdir_mount and workdir_mount.strip()):
        raise ValueError("build_jail_spec: blank workdir_mount — refusing")
    _reject_sensitive_mount(workdir_mount.strip())
    for e in env_passthrough:
        if "=" in e:
            raise ValueError(f"env_passthrough must be NAMES only (no values) — got {e!r} (no secret on disk)")
    allow = tuple(egress_allowlist(palace_mcp_url, provider))
    network_name = f"neop-{pid}-{nid}"            # per-seat network; the egress firewall binds to it
    args: List[str] = [
        "--rm",
        "--network", network_name,                 # NOT the default bridge — egress firewalled to `allow`
        "--read-only",                             # immutable rootfs
        "--cap-drop", "ALL",                       # no Linux capabilities
        "--security-opt", "no-new-privileges",     # no setuid escalation
        "--pids-limit", str(PIDS_LIMIT),
        "--memory", MEMORY, "--cpus", CPUS,
        "--tmpfs", TMPFS,                          # writable scratch only, noexec
        "--workdir", CONTAINER_WORKDIR,
        "-v", f"{workdir_mount}:{CONTAINER_WORKDIR}",   # the ONLY host bind — the jailed working dir
    ]
    for name in sorted(env_passthrough):           # `-e NAME` forwards the var by name; value stays in env
        args += ["-e", name]
    return JailSpec(seat=seat, image=image, network_name=network_name, egress_allowlist=allow,
                    env_passthrough=tuple(sorted(env_passthrough)), docker_args=tuple(args),
                    workdir_mount=workdir_mount)


class IsolationUnit:
    """Launches/tears down per-seat jails. `build_jail_spec` (policy) is offline-tested; `launch`/`teardown`
    perform the BOX-GATED exec (Docker + the egress firewall) and are validated at T0 on a box with Docker."""

    def egress_allowlist(self, palace_mcp_url: str, provider: str = ANTHROPIC_PROVIDER) -> List[str]:
        return egress_allowlist(palace_mcp_url, provider)

    def launch(self, seat: SeatId, image: str, env: Dict[str, str], workdir_mount: str, *,
               palace_mcp_url: str, provider: str = ANTHROPIC_PROVIDER) -> Handle:
        # Build + validate the fail-closed spec OFFLINE (raises before any container starts).
        spec = build_jail_spec(seat, image, palace_mcp_url=palace_mcp_url, workdir_mount=workdir_mount,
                               env_passthrough=sorted(env.keys()), provider=provider)
        return self._docker_run(spec, env)        # box-gated boundary

    def _docker_run(self, spec: "JailSpec", env: Dict[str, str]) -> Handle:
        # BOX-GATED (T0): create the per-seat network + egress firewall enforcing spec.egress_allowlist,
        # then `docker run <spec.docker_args> <spec.image>`. Not runnable in the WSL dev box.
        raise NotImplementedError(
            "box-gated: run on the T0 box (Docker). The fail-closed spec is built+validated above; this "
            "step starts the container + applies the egress firewall to spec.egress_allowlist.")

    def teardown(self, handle: Handle) -> None:
        raise NotImplementedError("box-gated: docker rm + drop the per-seat network (T0 box)")
