"""NEop-spec conformance linter — enforces the agent-patterns classification + gates at BUILD time.

Reference: `agents/AGENT_PATTERNS.md` (Anthropic "Building Effective Agents", mapped to NEOS). The
runtime loader `core.py` stays byte-identical; THIS is a separate, pure spec-conformance pass so every
NEop declares its pattern and autonomous NEops carry their stop/feedback gates BEFORE they run — not
left to per-agent discretion. Wired into CI via `tests/test_neop_spec.py` (runs over `agents/*/`).

The classification dimension (a `pattern:` frontmatter key, ignored by core, required here):
  * augmented_call — a single augmented LLM/tool call (one step, no loop). The simplest thing.
  * workflow       — a PREDEFINED code path orchestrating steps (prompt-chain / route / parallel /
                     pre-wired orchestrator-workers). Deterministic structure; the autonomy, if any,
                     is only in content, not control flow.
  * agent          — the LLM dynamically directs its own process: plan → execute → verify(env
                     feedback) → replan, under a hard iteration cap. Use ONLY when the task is
                     genuinely open-ended (simplicity-first: don't default to autonomous).

Gates enforced here (see AGENT_PATTERNS.md for all six):
  G1 every NEop declares a valid pattern (don't default to autonomous).
  G2 an `agent` carries a hard, sane iteration cap (`limits.max_replans`, bounded) → stop/escalate.
  G3 an `agent`'s role runs VERIFY (consumes environment feedback each step, not just at the end).
  G5 (soft) ACI: declared tools resolve to a `tools.json` surface.
Simplicity check: an `augmented_call` that pays the full plan/verify pipeline is mislabeled.
"""
from __future__ import annotations

import pathlib

import yaml

from runtime.core import DEFAULT_PHASE_SET, PHASE_SETS, Phase

PATTERNS = ("augmented_call", "workflow", "agent")
MAX_REPLAN_CEILING = 10  # a hard cap must be SANE — None / huge means effectively unbounded


def _frontmatter(neop_md: pathlib.Path):
    parts = neop_md.read_text().split("---", 2)
    if len(parts) < 3:
        return None
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None


def _runs_verify(role_family) -> bool:
    return Phase.VERIFY in PHASE_SETS.get(role_family, DEFAULT_PHASE_SET)


def lint_spec(folder) -> list[dict]:
    """Findings [{severity, code, msg}] for one agents/<name>/ folder. Empty list = conformant."""
    folder = pathlib.Path(folder)
    out: list[dict] = []

    def err(code, msg):
        out.append({"severity": "error", "code": code, "msg": f"{folder.name}: {msg}"})

    def warn(code, msg):
        out.append({"severity": "warning", "code": code, "msg": f"{folder.name}: {msg}"})

    fm = _frontmatter(folder / "neop.md")
    if fm is None:
        err("no_frontmatter", "neop.md missing or has invalid frontmatter")
        return out

    pattern = fm.get("pattern")
    # G1 — classify every NEop; never default to autonomous.
    if pattern is None:
        err("missing_pattern", "no `pattern:` — declare augmented_call|workflow|agent (G1)")
        return out
    if pattern not in PATTERNS:
        err("bad_pattern", f"pattern '{pattern}' not in {PATTERNS} (G1)")
        return out

    rf = fm.get("role_family")
    limits = fm.get("limits") if isinstance(fm.get("limits"), dict) else {}

    if pattern == "agent":
        # G3 — an agent must consume environment feedback each step: its role must run VERIFY.
        if not _runs_verify(rf):
            err("agent_no_verify",
                f"pattern=agent but role_family '{rf}' has no VERIFY phase — an agent must consume "
                "environment feedback each step (G3)")
        # G2 — a hard, bounded iteration cap (the stop/escalate condition).
        mr = limits.get("max_replans")
        if not isinstance(mr, int) or mr < 0 or mr > MAX_REPLAN_CEILING:
            err("agent_unbounded",
                f"pattern=agent needs a bounded limits.max_replans in [0,{MAX_REPLAN_CEILING}] "
                f"(got {mr!r}) — a hard iteration cap, else cost/error compound silently (G2)")
    elif pattern == "augmented_call":
        # simplicity: a single augmented call should not pay the full plan/verify pipeline.
        if _runs_verify(rf):
            warn("augmented_overpays",
                 f"pattern=augmented_call but role_family '{rf}' runs the plan/verify pipeline — "
                 "reclassify as workflow|agent, or use an execute-only role (simplicity-first)")

    # G5 (soft) — ACI: a declared tool surface must resolve to tools.json.
    declared = fm.get("tools") or []
    if declared and not (folder / "tools.json").exists():
        warn("aci_no_tools_json", f"declares tools {declared} but has no tools.json (ACI surface, G5)")

    return out


def lint_all(agents_dir) -> list[dict]:
    """Lint every discovered NEop (mirrors nrt discovery: agents/*/neop.md)."""
    agents_dir = pathlib.Path(agents_dir)
    out: list[dict] = []
    for folder in sorted(p.parent for p in agents_dir.glob("*/neop.md")):
        out.extend(lint_spec(folder))
    return out


def errors(findings) -> list[dict]:
    return [f for f in findings if f["severity"] == "error"]


def warnings(findings) -> list[dict]:
    return [f for f in findings if f["severity"] == "warning"]
