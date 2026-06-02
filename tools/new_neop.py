#!/usr/bin/env python3
"""new_neop — scaffold a NEop that is BORN memory+twin-attached.

The default posture (memory:{read:true} + twin:{read:true}, write deliberate) is baked
in here, so a new catalog NEop can't forget it — "attach altogether" by construction,
not per-NEop discipline. Harness instruments (--harness) scaffold memory-less, like
echo/ping. The generated NEop is green out of the box: `nrt validate` + `nrt test` pass.

Usage:
  python3 tools/new_neop.py <id> [--role meta|sales|research|reactive|executor]
        [--tools t1,t2] [--harness] [--writes-memory] [--writes-twin] [--out DIR] [--force]
"""
from __future__ import annotations
import argparse, json, pathlib

PHASE_SETS = {
    "meta": ["plan", "execute", "verify"], "sales": ["plan", "execute", "verify"],
    "research": ["plan", "execute", "verify"], "reactive": ["execute", "verify"],
    "executor": ["execute"],
}


def _yaml_bool(b):
    return "true" if b else "false"


def build(nid, role, tools, harness, writes_mem, writes_twin):
    phases = PHASE_SETS.get(role, PHASE_SETS["meta"])
    primary = tools[0]
    model = ("{ planner: stub, executor: stub, verifier: stub }" if "plan" in phases
             else "{ executor: stub, verifier: stub }" if "verify" in phases
             else "{ executor: stub }")
    fm = ["---", f"neop_id: {nid}", "version: 1", f"role_family: {role}",
          f"model: {model}", "limits: { max_replans: 2 }"]
    if not harness:                              # the default posture — born grounded
        fm.append(f"memory: {{ read: true, write: {_yaml_bool(writes_mem)} }}")
        fm.append("twin: { read: true, write: true }" if writes_twin else "twin: { read: true }")
    fm += [f"tools: [{', '.join(tools)}]", f"acp: {{ publishes: [{nid}] }}", "---",
           f"# {nid.capitalize()} NEop",
           "Scaffolded NEop — replace this prose, the subagent prompts, and the fixtures with real content."]
    files = {"neop.md": "\n".join(fm) + "\n", "tools.json": json.dumps(tools) + "\n",
             "executor.md": f"You are the EXECUTOR for `{nid}`. Call the task's declared tool.\n"}
    if "plan" in phases:
        files["planner.md"] = (f"You are the PLANNER for `{nid}`. Output ONLY JSON:\n"
                               f'{{"tasks": [{{"task_id": "t1", "tool": "{primary}", "depends_on": []}}]}}\n')
    if "verify" in phases:
        files["verifier.md"] = (f"You are the VERIFIER for `{nid}`. Output ONLY JSON: "
                                '{"pass": true} or {"pass": false}.\n')

    case = f"{nid}_smoke"
    golden = {"tasks": [{"task_id": "t1", "tool": primary, "depends_on": []}]}
    files["fixtures/golden_plan.json"] = json.dumps(golden, indent=2) + "\n"
    files["fixtures/mocks/tools.json"] = json.dumps({primary: {"$reflect_field": "text"}}, indent=2) + "\n"
    expect = {"terminal_state": "DONE", "expected_phases": phases, "golden_plan": "golden_plan.json",
              "must_call_tools": [primary], "max_replans": 0}
    inp = {"text": "hello", "tenant": "neuraledge", "seat": nid}
    files["fixtures/eval.jsonl"] = json.dumps({"case_id": case, "input": inp, "expect": expect}) + "\n"
    cass = {}
    if "plan" in phases:
        cass[f"plan:{nid}"] = golden
    if "verify" in phases:
        cass[f"verify:{nid}"] = {"pass": True}
    if cass:
        files[f"fixtures/cassettes/{case}.json"] = json.dumps(cass, indent=2) + "\n"
    if not harness:                              # grounding bundle (assemble retrieves)
        files[f"fixtures/memory/{case}.json"] = json.dumps({
            "chunks": [{"id": "m1", "tenant": "neuraledge", "text": f"seed grounding for {nid}",
                        "score": 0.6, "category": "fact", "source_adapter": "mcp", "confidence": 0.5}],
            "provenance": [{"id": "m1", "source_adapter": "mcp", "author_type": "human",
                            "author_id": "ml", "created_at": 1700000000}]}, indent=2) + "\n"
    return files, phases


def main(argv=None):
    ap = argparse.ArgumentParser(prog="new_neop")
    ap.add_argument("id")
    ap.add_argument("--role", default="meta", choices=list(PHASE_SETS))
    ap.add_argument("--tools", default="")
    ap.add_argument("--harness", action="store_true", help="memory-less test instrument")
    ap.add_argument("--writes-memory", action="store_true", help="this NEop persists observations")
    ap.add_argument("--writes-twin", action="store_true", help="twin-lifecycle NEop (Interviewer/Curator)")
    ap.add_argument("--out", default="agents")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    tools = [t.strip() for t in a.tools.split(",") if t.strip()] or [f"{a.id}_tool"]
    root = pathlib.Path(a.out) / a.id
    if root.exists() and not a.force:
        print(f"refusing to overwrite {root} (use --force)")
        return 1
    files, phases = build(a.id, a.role, tools, a.harness, a.writes_memory, a.writes_twin)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    posture = "harness (memory-less)" if a.harness else "memory:{read} + twin:{read}"
    print(f"scaffolded {root}/ ({len(files)} files) role={a.role} phases={phases} tools={tools}")
    print(f"  posture: {posture}")
    print(f"  verify:  python3 nrt/cli.py validate {root} && python3 nrt/cli.py test {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
