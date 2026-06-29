"""`python -m neop_jcode_adapter` — the adapter entrypoint T0 invokes.

Two commands:
  preflight  — build a SeatSpec from env and run the fail-closed go/no-go (RUNNABLE anywhere; honestly
               reports not-ready off the box). Exit 0 = ready, 1 = a prerequisite is missing.
  launch     — preflight → assemble → hand to the supervisor (the box-gated spawn). Needs the T0 box.

Seat inputs come from env (scope is env-baked, never the model): PALACE_ID, NEOP_ID, NEOP_SEAT_CLASS,
PALACE_MCP_URL, NEOP_IMAGE, NEOP_WORKDIR, JCODE_HOME, NEOP_PROVIDER, NEOP_MODEL_ID,
PALACE_SIGNING_KEY_REF, NEOP_ENABLE_GET_CLOSET, NEOP_JAIL_ENFORCED.
"""
from __future__ import annotations

import argparse
import os
import sys

from .seat_adapter import SeatSpec, preflight, assemble, launch
from .config_render import ANTHROPIC_PROVIDER
from .audit_tap import AuditTap
from .event_bridge import EventBridge
from .supervisor import SeatSupervisor


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def spec_from_env(env=None) -> SeatSpec:
    env = env if env is not None else os.environ
    return SeatSpec(
        palace_id=env.get("PALACE_ID", ""),
        neop_id=env.get("NEOP_ID", ""),
        seat_class=env.get("NEOP_SEAT_CLASS", "C"),
        palace_mcp_url=env.get("PALACE_MCP_URL", ""),
        image=env.get("NEOP_IMAGE", ""),
        workdir_mount=env.get("NEOP_WORKDIR", ""),
        jcode_home=env.get("JCODE_HOME", ""),
        provider=env.get("NEOP_PROVIDER", ANTHROPIC_PROVIDER),
        model_id=env.get("NEOP_MODEL_ID") or None,
        signing_key_ref=env.get("PALACE_SIGNING_KEY_REF") or None,
        enable_get_closet=_truthy(env.get("NEOP_ENABLE_GET_CLOSET")),
        jail_enforced=_truthy(env.get("NEOP_JAIL_ENFORCED")),
    )


def _print_report(report) -> None:
    for w in report.warnings:
        print(f"  warn: {w}", file=sys.stderr)
    if report.ok:
        print("preflight: READY")
    else:
        print("preflight: NOT READY", file=sys.stderr)
        for f in report.failures:
            print(f"  fail: {f}", file=sys.stderr)


def cmd_preflight(args) -> int:
    report = preflight(spec_from_env())
    _print_report(report)
    return 0 if report.ok else 1


def cmd_launch(args) -> int:
    spec = spec_from_env()
    report = preflight(spec)
    _print_report(report)
    if not report.ok:
        return 1
    audit = AuditTap()                          # NEOP_AUDIT_DIR or raises (no silent audit-nowhere)
    events = EventBridge()                       # NEOP_EVENT_LOG or raises
    assembled = assemble(spec, audit=audit, events=events)
    launch(assembled, SeatSupervisor(), skip_preflight=True)  # spawn is box-gated → raises off the box
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="neop_jcode_adapter")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight", help="go/no-go check (runnable anywhere)")
    sub.add_parser("launch", help="preflight + assemble + launch (needs the T0 box)")
    args = p.parse_args(argv)
    return {"preflight": cmd_preflight, "launch": cmd_launch}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
