"""SeatAdapter — the per-seat ASSEMBLY that wires the adapter's parts into one launch.

Until now the components existed only as separate units (shim · config_render · isolation · supervisor ·
audit_tap · event_bridge). This is the glue T0 actually invokes: given one seat's inputs it (1) runs a
**fail-closed preflight** (every prerequisite present before anything starts), (2) **assembles** the seat
offline — the scope-locked shim, the rendered jcode config, the validated jail spec, the audit + event
taps — and (3) hands off to the supervisor to **launch**. Steps 1–2 are pure and offline-tested; only the
launch bottoms out in the existing box-gated boundaries (`SeatSupervisor._spawn` / `IsolationUnit._docker_run`).

Fail-closed throughout (CLAUDE.md): scope is (palaceId, neopId), env-baked, never `_admin`/`_system`;
the jail egress is palace + model host only; the model key rides env (never a config/arg value).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .config_render import (
    ANTHROPIC_PROVIDER, OPENROUTER_PROVIDER, OPENROUTER_API_KEY_ENV,
    ConfigRenderer, RenderedSeat)
from .isolation import build_jail_spec, JailSpec
from .palace_mcp_shim import PalaceShim, RESERVED_IDENTITIES
from .seat_classes import preset_for
from .audit_tap import AuditTap
from .event_bridge import EventBridge

# Which env var each provider reads its key from (jcode reads it automatically; never a config value).
PROVIDER_KEY_ENV = {
    ANTHROPIC_PROVIDER: "ANTHROPIC_API_KEY",
    OPENROUTER_PROVIDER: OPENROUTER_API_KEY_ENV,
}


@dataclass(frozen=True)
class SeatSpec:
    """Everything needed to stand up one seat. Scope + class + the live endpoints; no secrets inline
    (keys ride env by NAME, the signing key is a keyref the shim resolves)."""
    palace_id: str
    neop_id: str
    seat_class: str                      # "A" | "B" | "C"
    palace_mcp_url: str
    image: str                           # the jail container image
    workdir_mount: str                   # the per-seat host workdir (the jail's one writable bind)
    jcode_home: str                      # per-seat $JCODE_HOME (config.toml + mcp.json land here)
    provider: str = ANTHROPIC_PROVIDER
    model_id: Optional[str] = None
    signing_key_ref: Optional[str] = None   # "env:NAME" | "file:PATH" (forward-looking, Gate D)
    enable_get_closet: bool = False
    jail_enforced: bool = False          # True only where a live Docker jail is asserted (Class A gate)


@dataclass
class PreflightReport:
    ok: bool
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _key_env_name(provider: str) -> Optional[str]:
    return PROVIDER_KEY_ENV.get(provider)


def _default_docker_probe() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except Exception:
        return False


def _default_jcode_probe() -> bool:
    return shutil.which("jcode") is not None


def preflight(spec: SeatSpec, *, env: Optional[Dict[str, str]] = None,
              docker_probe: Optional[Callable[[], bool]] = None,
              jcode_probe: Optional[Callable[[], bool]] = None) -> PreflightReport:
    """Fail-closed go/no-go: collect EVERY missing prerequisite (don't stop at the first) so the operator
    sees the whole gap at once. The offline checks (scope/class/provider/key-env/url) are hard failures;
    the box checks (Docker reachable, jcode present) run via injected probes — defaulting to real probes,
    so on a box without them this honestly reports not-ready rather than pretending."""
    env = env if env is not None else dict(os.environ)
    fails: List[str] = []
    warns: List[str] = []

    # scope — non-blank and not a privileged identity (the _admin/_system bypass family)
    for label, val in (("PALACE_ID", spec.palace_id), ("NEOP_ID", spec.neop_id)):
        if not (val and val.strip()):
            fails.append(f"{label} is blank (would default server-side to _admin = ACL bypass)")
        elif val.strip() in RESERVED_IDENTITIES:
            fails.append(f"{label} '{val.strip()}' is a reserved privileged identity")
    if not (spec.palace_mcp_url and spec.palace_mcp_url.strip()):
        fails.append("PALACE_MCP_URL is blank")
    if not (spec.image and spec.image.strip()):
        fails.append("image is blank")
    if not (spec.workdir_mount and spec.workdir_mount.strip()):
        fails.append("workdir_mount is blank")

    # seat class must be known
    try:
        preset_for(spec.seat_class)
    except (KeyError, ValueError):
        fails.append(f"unknown seat_class {spec.seat_class!r} (want A|B|C)")

    # Class A's loose posture REQUIRES an enforced jail (the container is its sandbox)
    if str(spec.seat_class).upper() == "A" and not spec.jail_enforced:
        warns.append("Class A without jail_enforced=True renders as a WORKER (no bash/swarm) — "
                     "assert the live jail to grant Class A its posture")

    # provider + the model key it reads from env
    key_env = _key_env_name(spec.provider)
    if key_env is None:
        fails.append(f"unknown provider {spec.provider!r} (want {sorted(PROVIDER_KEY_ENV)})")
    elif not env.get(key_env):
        fails.append(f"model key env {key_env} is unset (the live NEop dispatch needs it)")

    # signing key (forward-looking; warn, don't fail — /mcp doesn't verify it yet, Gate D)
    if spec.signing_key_ref:
        scheme = spec.signing_key_ref.split(":", 1)[0]
        if scheme == "env" and not env.get(spec.signing_key_ref.split(":", 1)[1]):
            warns.append(f"signing key env {spec.signing_key_ref} is unset (Gate-D forward-looking)")
        elif scheme not in ("env", "file"):
            fails.append(f"signing_key_ref scheme {scheme!r} unsupported (use env:|file:)")
    else:
        warns.append("no signing_key_ref — shim runs unsigned (acceptable pre-Gate-D)")

    # box prerequisites (injected so the LOGIC is offline-testable; real probes by default)
    if (docker_probe or _default_docker_probe)() is not True:
        fails.append("Docker daemon not reachable (T0 box requirement)")
    if (jcode_probe or _default_jcode_probe)() is not True:
        fails.append("jcode binary not found on PATH (T0 box requirement)")

    return PreflightReport(ok=not fails, failures=fails, warnings=warns)


@dataclass
class AssembledSeat:
    spec: SeatSpec
    shim: PalaceShim
    rendered: RenderedSeat
    jail_spec: JailSpec
    audit: AuditTap
    events: EventBridge
    env_passthrough: List[str]           # NAMES the jail forwards (no values — no secret on disk)
    hook_env: Dict[str, str]             # NEOP_* policy values the launcher must set before spawn

    @property
    def seat(self):
        return (self.spec.palace_id, self.spec.neop_id)


def assemble(spec: SeatSpec, *, audit: AuditTap, events: EventBridge,
             renderer: Optional[ConfigRenderer] = None, write: bool = True) -> AssembledSeat:
    """Build the whole seat OFFLINE (no container, no network). Each sub-build re-validates fail-closed,
    so a bad spec raises here — long before any exec. `write=False` keeps it a dry assembly (tests)."""
    renderer = renderer or ConfigRenderer()
    preset = preset_for(spec.seat_class)
    cls = preset.seat_class.value

    # The scope-locked shim (re-validates blank/reserved scope; bakes scope from spec, never the model).
    shim = PalaceShim(
        palace_url=spec.palace_mcp_url, palace_id=spec.palace_id, neop_id=spec.neop_id,
        signing_key_ref=spec.signing_key_ref, enable_get_closet=spec.enable_get_closet,
        audit=audit.emit)

    # The per-seat jcode config — the pre_tool hook is wired so the ask/allow tier is real (T5).
    pre_tool_cmd = renderer.pre_tool_command()
    rendered = renderer.render(
        palace_id=spec.palace_id, neop_id=spec.neop_id, seat_class=cls, jcode_home=spec.jcode_home,
        palace_mcp_url=spec.palace_mcp_url, signing_key_ref=spec.signing_key_ref or "",
        model_id=spec.model_id, provider=spec.provider, pre_tool_hook=pre_tool_cmd,
        enable_get_closet=spec.enable_get_closet, jail_enforced=spec.jail_enforced,
        swarm_enabled=preset.swarm_enabled, write=write)

    # The hook's baked policy (read from env inside the jail) — VALUES the launcher sets, NAMES forwarded.
    hook_env = ConfigRenderer.hook_env(cls, swarm_enabled=preset.swarm_enabled,
                                       jail_enforced=spec.jail_enforced)

    # env the jail forwards: the model key + signing key (env: scheme) + the hook policy vars. NAMES only.
    names = set(hook_env.keys())
    key_env = _key_env_name(spec.provider)
    if key_env:
        names.add(key_env)
    if spec.signing_key_ref and spec.signing_key_ref.startswith("env:"):
        names.add(spec.signing_key_ref.split(":", 1)[1])
    env_passthrough = sorted(names)

    jail_spec = build_jail_spec(
        (spec.palace_id, spec.neop_id), spec.image, palace_mcp_url=spec.palace_mcp_url,
        workdir_mount=spec.workdir_mount, env_passthrough=env_passthrough, provider=spec.provider)

    return AssembledSeat(spec=spec, shim=shim, rendered=rendered, jail_spec=jail_spec,
                         audit=audit, events=events, env_passthrough=env_passthrough, hook_env=hook_env)


def launch(assembled: AssembledSeat, supervisor, *, skip_preflight: bool = False,
           env: Optional[Dict[str, str]] = None) -> object:
    """Box-gated thin glue: preflight (unless skipped) → emit `started` → supervisor.start (the box-gated
    spawn). Refuses to launch if preflight fails. The lifecycle event is emitted BEFORE the spawn so a
    crashing start still leaves a trail (the audit/event stream is the leak-detector)."""
    if not skip_preflight:
        report = preflight(assembled.spec, env=env)
        if not report.ok:
            raise RuntimeError("preflight failed: " + "; ".join(report.failures))
    assembled.events.started(assembled.seat, seat_class=assembled.spec.seat_class)
    return supervisor.start(assembled.seat, preset_for(assembled.spec.seat_class))
