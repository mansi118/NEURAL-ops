"""nrt — NEOS Runtime Tester (v2, Pi-informed).

  nrt validate <agent>          diagnostics-as-data (all defects, not first)
  nrt test     <agent>          run fixtures (unit), assert on typed result
  nrt trace    <agent> --case   dump the typed event stream
  nrt suite    <dir>            CI entrypoint
  nrt golden   <agent> --record (next increment)
"""
from __future__ import annotations
import json, sys, pathlib, argparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runtime.core import dispatch, load_neop  # noqa: E402


def load_fixtures(agent):
    cases, ev = [], agent / "fixtures" / "eval.jsonl"
    if ev.exists():
        for line in ev.read_text().splitlines():
            if line.strip():
                cases.append(json.loads(line))
    return cases


def load_json(p, default=None):
    p = pathlib.Path(p)
    return json.loads(p.read_text()) if p.exists() else default


def structural_plan(plan):
    if not plan:
        return {}
    tasks = plan["tasks"]
    return {
        "tasks": sorted(t["task_id"] for t in tasks),
        "edges": sorted([t["task_id"] + "<-" + d for t in tasks for d in t.get("depends_on", [])]),
        "tools": sorted([t["task_id"] + ":" + str(t.get("tool")) for t in tasks]),
    }


def assert_case(result, expect, golden):
    fails = []
    if result["state"] != expect.get("terminal_state"):
        fails.append(f"terminal_state {result['state']} != {expect.get('terminal_state')}")
    if "expected_phases" in expect and result.get("phases") != expect["expected_phases"]:
        fails.append(f"phases {result.get('phases')} != {expect['expected_phases']}")
    if golden is not None and structural_plan(result.get("plan")) != structural_plan(golden):
        fails.append("plan structural mismatch vs golden_plan")
    called = [c["tool"] for c in result.get("tool_calls", []) if c["allowed"]]
    attempted = [c["tool"] for c in result.get("tool_calls", [])]
    for t in expect.get("must_call_tools", []):
        if t not in called:
            fails.append(f"must_call_tools: '{t}' never called")
    for t in expect.get("must_not_call_tools", []):
        if t in attempted:
            fails.append(f"must_not_call_tools: '{t}' attempted")
    if "max_replans" in expect and result.get("replans", 0) > expect["max_replans"]:
        fails.append(f"replans {result['replans']} > {expect['max_replans']}")
    if "max_latency_s" in expect and result.get("total_ms", 0) > expect["max_latency_s"] * 1000:
        fails.append(f"latency {result['total_ms']}ms > {expect['max_latency_s']}s")
    return fails


def run_case(agent, case, mode):
    fx = agent / "fixtures"
    cas = load_json(fx / "cassettes" / f"{case['case_id']}.json", {}) or {}
    mocks = load_json(fx / "mocks" / "tools.json", {}) or {}
    result = dispatch(agent, case["input"], mode, cas, mocks, case.get("stm", []))
    expect = case.get("expect", {})
    golden = load_json(fx / expect["golden_plan"]) if expect.get("golden_plan") else None
    return result, assert_case(result, expect, golden)


def _print_diags(diags):
    for d in diags or []:
        mark = "x" if d["severity"] == "error" else "!"
        print(f"        [{mark}] {d['code']}: {d['msg']}")


def cmd_validate(agent):
    defn, diags = load_neop(agent)
    if defn is None:
        print(f"  FAIL  {agent.name}")
        _print_diags(diags)
        return 1
    print(f"  OK    {defn['id']} v{defn['version']} · role_family={defn['role_family']} "
          f"· phases={[p.value for p in defn['phases']]} · tools={defn['tools']}")
    _print_diags(diags)  # warnings, if any
    return 0


def cmd_test(agent, mode):
    cases = load_fixtures(agent)
    if not cases:
        print("  no fixtures/eval.jsonl"); return 1
    rc = 0
    for c in cases:
        result, fails = run_case(agent, c, mode)
        if fails:
            rc = 1
            print(f"  FAIL  {c['case_id']}  [{mode}]")
            for f in fails:
                print(f"          - {f}")
        else:
            print(f"  PASS  {c['case_id']}  [{mode}]  state={result['state']} "
                  f"phases={result.get('phases')} replans={result['replans']} {result['total_ms']}ms")
    return rc


def cmd_trace(agent, case_id, mode):
    cases = [c for c in load_fixtures(agent) if c["case_id"] == case_id]
    if not cases:
        print(f"  no case '{case_id}'"); return 1
    result, fails = run_case(agent, cases[0], mode)
    print("EVENT STREAM:")
    for e in result.get("events", []):
        extra = {k: v for k, v in e.items() if k not in ("event", "t_ms")}
        print(f"  {e['t_ms']:>4}ms  {e['event']:<13} {json.dumps(extra) if extra else ''}")
    print("RESULT:", "PASS" if not fails else f"FAIL {fails}")
    return 0 if not fails else 1


def cmd_suite(root, mode):
    root, rc = pathlib.Path(root), 0
    for agent in sorted(p.parent for p in root.glob("*/neop.md")):
        print(f"# {agent.name}")
        rc |= cmd_validate(agent)
        rc |= cmd_test(agent, mode)
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="nrt")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "test", "trace"):
        s = sub.add_parser(name)
        s.add_argument("agent")
        s.add_argument("--mode", default="unit")
        if name == "trace":
            s.add_argument("--case", required=True)
    s = sub.add_parser("suite"); s.add_argument("dir"); s.add_argument("--mode", default="unit")
    s = sub.add_parser("golden"); s.add_argument("agent"); s.add_argument("--record", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "validate": return cmd_validate(pathlib.Path(a.agent))
    if a.cmd == "test": return cmd_test(pathlib.Path(a.agent), a.mode)
    if a.cmd == "trace": return cmd_trace(pathlib.Path(a.agent), a.case, a.mode)
    if a.cmd == "suite": return cmd_suite(a.dir, a.mode)
    if a.cmd == "golden": print("  golden --record needs integration mode — next increment."); return 0


if __name__ == "__main__":
    raise SystemExit(main())
