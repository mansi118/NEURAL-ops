"""NEOS runtime core (reference / test-mode) — v2, Pi-informed.

Loads a NEop folder, instantiates it as a Pi-agent, runs a phase set that is a
FUNCTION OF role_family, and emits a typed event stream. Production Hermes (Node)
implements the same contract; this Python core is the executable spec + the
permanent test runtime behind `nrt`.

Three things adopted from Pi (pi-agent-core), each justified by nrt/ACP, not by
the model needing rails:
  1. Diagnostics-as-data in the loader (collect, don't throw-on-first).
  2. A typed phase-event stream (one stream powers trace + assertions + future UI).
  3. Runtime tool-allowlist enforcement (contract enforced in prod, not just CI).
And the core structural fix the critique demanded:
  4. Phase set per role_family — a pure executor does NOT pay the plan+verify tax.
"""
from __future__ import annotations
import enum, json, time, hashlib, pathlib

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("pip install pyyaml")


# ============================================================ phases & states
class Phase(str, enum.Enum):
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"


# role_family -> ordered phase set. THIS is the "don't make every agent pay for
# features only some need" fix. A pure executor skips plan+verify entirely.
PHASE_SETS = {
    "meta":     [Phase.PLAN, Phase.EXECUTE, Phase.VERIFY],
    "sales":    [Phase.PLAN, Phase.EXECUTE, Phase.VERIFY],
    "research": [Phase.PLAN, Phase.EXECUTE, Phase.VERIFY],
    "executor": [Phase.EXECUTE],                       # no plan, no verify tax
    "reactive": [Phase.EXECUTE, Phase.VERIFY],         # verify but no upfront plan
}
DEFAULT_PHASE_SET = [Phase.PLAN, Phase.EXECUTE, Phase.VERIFY]


class State(str, enum.Enum):
    LOADING = "LOADING"
    REJECTED = "REJECTED"
    ASSEMBLING = "ASSEMBLING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    VERIFYING = "VERIFYING"
    REPLANNING = "REPLANNING"
    DONE = "DONE"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


TERMINAL = {State.DONE, State.FAILED, State.ESCALATED, State.REJECTED}


# ============================================================ typed event stream (steal #2)
# One typed union, emitted by the run, consumed by nrt trace / assertions / future UI.
EVENT_TYPES = {
    "run_start", "assemble", "memory_retrieve", "memory_write",
    "plan_start", "plan_end",
    "tool_call", "tool_result", "tool_blocked",
    "verify_start", "verify_end", "replan", "escalate", "run_end",
}


def event(kind, t0, **fields):
    assert kind in EVENT_TYPES, f"unknown event '{kind}'"
    return {"event": kind, "t_ms": round((time.time() - t0) * 1000), **fields}


# ============================================================ loader (steal #1: diagnostics-as-data)
REQUIRED_FRONTMATTER = ["neop_id", "version", "limits"]


def _split_frontmatter(text):
    if not text.startswith("---"):
        return None, "missing frontmatter fence '---'"
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, "malformed frontmatter"
    try:
        return (yaml.safe_load(parts[1]) or {}), None
    except yaml.YAMLError as e:
        return None, f"yaml parse error: {e}"


def load_neop(folder):
    """Return (defn_or_None, diagnostics[]). Collects ALL defects; never throws on first.
    diagnostic = {severity: error|warning, code, msg}."""
    folder = pathlib.Path(folder)
    diags = []

    def err(code, msg): diags.append({"severity": "error", "code": code, "msg": msg})
    def warn(code, msg): diags.append({"severity": "warning", "code": code, "msg": msg})

    neop_md = folder / "neop.md"
    if not neop_md.exists():
        err("missing_neop_md", f"no neop.md in {folder}")
        return None, diags

    fm, perr = _split_frontmatter(neop_md.read_text())
    if perr:
        err("parse_failed", perr)
        return None, diags

    for k in REQUIRED_FRONTMATTER:
        if k not in fm:
            err("invalid_metadata", f"frontmatter missing required key '{k}'")

    tools = []
    tj = folder / "tools.json"
    if tj.exists():
        try:
            tools = json.loads(tj.read_text())
        except json.JSONDecodeError as e:
            err("parse_failed", f"tools.json: {e}")

    declared = fm.get("tools", []) if isinstance(fm, dict) else []
    for t in declared:
        if t not in tools:
            err("unknown_tool", f"frontmatter tool '{t}' not in tools.json {tools}")

    rf = fm.get("role_family") if isinstance(fm, dict) else None
    if rf and rf not in PHASE_SETS:
        warn("unknown_role_family", f"role_family '{rf}' has no phase set; using default")

    # missing optional subagent files for phases this role will run -> warnings
    phases = PHASE_SETS.get(rf, DEFAULT_PHASE_SET)
    if Phase.PLAN in phases and not (folder / "planner.md").exists():
        warn("missing_subagent", "planner.md absent but role runs PLAN")
    if Phase.VERIFY in phases and not (folder / "verifier.md").exists():
        warn("missing_subagent", "verifier.md absent but role runs VERIFY")

    if any(d["severity"] == "error" for d in diags):
        return None, diags

    def read(name):
        p = folder / name
        return p.read_text() if p.exists() else ""

    defn = {
        "id": fm["neop_id"], "version": fm["version"], "frontmatter": fm,
        "role_family": rf, "phases": phases,
        "role": _split_frontmatter(neop_md.read_text())[0] and neop_md.read_text().split("---", 2)[2].strip(),
        "planner": read("planner.md"), "executor": read("executor.md"),
        "verifier": read("verifier.md"), "tools": tools, "folder": folder,
    }
    return defn, diags


# ============================================================ brokers
def cassette_key(phase, prompt):
    return f"{phase}:{hashlib.sha256(prompt.encode()).hexdigest()[:16]}"


class ModelBroker:
    def __init__(self, mode, cassette=None):
        self.mode, self.cassette = mode, (cassette or {})

    def call(self, phase, prompt):
        if self.mode != "unit":
            raise RuntimeError(f"mode '{self.mode}' not wired in step-1 reference (unit only)")
        key = cassette_key(phase, prompt)
        if key in self.cassette:
            return self.cassette[key]
        cands = [v for k, v in self.cassette.items() if k.startswith(phase + ":")]
        if len(cands) == 1:
            return cands[0]
        raise RuntimeError(f"cassette miss for {key} — run `nrt golden --record`")


class ToolBroker:
    """steal #3: allowlist enforced AT RUNTIME. Unknown tool -> blocked result the
    agent could self-correct on, AND a tool_blocked event. Not merely a CI assertion."""
    def __init__(self, mode, mocks, allowlist):
        self.mode, self.mocks = mode, mocks
        self.allowlist = set(allowlist)
        self.calls = []  # [{tool, allowed}]

    def invoke(self, tool, args):
        allowed = tool in self.allowlist
        self.calls.append({"tool": tool, "allowed": allowed})
        if not allowed:
            return {"_blocked": True, "reason": f"tool '{tool}' not in allowlist {sorted(self.allowlist)}"}
        if self.mode not in ("unit", "integration"):
            raise RuntimeError("live tools not wired in step-1 reference")
        if tool not in self.mocks:
            raise RuntimeError(f"no mock for tool '{tool}'")
        m = self.mocks[tool]
        if isinstance(m, dict) and "$reflect_field" in m:
            f = m["$reflect_field"]
            return {f: args.get(f)}
        return m


class MemoryBroker:
    """Third deterministic seam. The Pi-agent only calls retrieve()/write()/consolidate();
    whether that resolves to a recorded bundle (unit) or live MemPalace (integration) is
    broker-internal. MemPalace is a FACADE over Convex (system-of-record + vector index) +
    Bedrock Titan embeddings; FalkorDB is advisory. Those details never touch the phase machine.

    unit        -> recorded bundle (fixtures/memory/<case>.json); no network.
    integration -> live MemPalace over HTTP (runtime.memory), lazy + credential-gated.
    """
    def __init__(self, mode, stm, *, bundle=None, provider=None):
        self.mode = mode
        self.stm = stm or []
        self.bundle = bundle or {}
        self.provider = provider
        self.writes = []
        self.consolidations = []

    def retrieve(self, tenant, seat, query, tiers=None, k=5):
        # tiers: MemPalace has no tier param (STM/LTM is implicit) -> accepted, advisory no-op.
        if self.mode == "unit":
            chunks = self.bundle.get("chunks", [])
            # tenant guard (P-5/6): a seat in tenant A never sees tenant B's chunks.
            visible = [c for c in chunks if c.get("tenant", tenant) == tenant][:k]
            ids = {c["id"] for c in visible}
            prov = [p for p in self.bundle.get("provenance", []) if p.get("id") in ids]
            return {"chunks": visible, "provenance": prov}
        if self.mode == "integration":
            return self._live().retrieve(tenant, seat, query, k=k)
        raise RuntimeError(f"memory mode '{self.mode}' not supported")

    def write(self, tenant, seat, record):
        prov = {"source_adapter": "neos-runtime",
                "source_external_id": f"{tenant}:{seat}:{len(self.writes)}",
                "author_type": "neop", "author_id": seat}
        stamped = {**record, "tenant": tenant, "seat": seat, "provenance": prov}
        if self.mode == "unit":
            self.writes.append(stamped)
            return {"status": "ok", "closet_id": f"unit-{len(self.writes)}",
                    "dedup_key": prov["source_external_id"]}
        if self.mode == "integration":
            return self._live().write(tenant, seat, stamped)
        raise RuntimeError(f"memory mode '{self.mode}' not supported")

    def consolidate(self, tenant, seat):
        # STM->LTM hook: real call site, stub body (no nightly cron yet).
        rec = {"tenant": tenant, "seat": seat, "promoted": len(self.stm)}
        self.consolidations.append(rec)
        return rec

    def _live(self):
        if self.provider is None:
            from runtime import memory as _m
            self.provider = _m
        return self.provider


# ============================================================ Pi-agent
class PiAgent:
    def __init__(self, defn, model, tools, memory):
        self.defn, self.model, self.tools, self.mem = defn, model, tools, memory
        self.phases = defn["phases"]
        self.state = State.LOADING
        self.events = []
        self.replans = 0
        self.max_replans = defn["frontmatter"]["limits"].get("max_replans", 2)
        self.plan = None
        self.outputs = {}
        self.mem_cfg = defn["frontmatter"].get("memory") or {}   # {read?, write?}
        self.bundle = {}                                          # chunks folded in at assemble
        self.t0 = time.time()

    def _e(self, kind, **f): self.events.append(event(kind, self.t0, **f))

    def run(self, msg):
        self._e("run_start", neop=self.defn["id"], role_family=self.defn["role_family"],
                 phases=[p.value for p in self.phases])
        self.state = State.ASSEMBLING
        self.bundle = {}
        if self.mem_cfg.get("read"):
            tenant, seat = msg.get("tenant", "default"), msg.get("seat", self.defn["id"])
            self.bundle = self.mem.retrieve(tenant, seat, msg.get("text", ""))
            self._e("memory_retrieve", tenant=tenant, seat=seat,
                    chunks=len(self.bundle.get("chunks", [])),
                    ids=[c["id"] for c in self.bundle.get("chunks", [])])
        self._e("assemble", stm=len(self.mem.stm))

        # PLAN (only if role runs it) — else synthesize a one-task implicit plan
        if Phase.PLAN in self.phases:
            self.plan = self._plan(msg)
        else:
            self.plan = self._implicit_plan(msg)

        while True:
            ok = self._execute_and_maybe_verify(self.plan, msg)
            if ok:
                self.state = State.DONE
                break
            if self.state == State.FAILED:
                break
            # replan only meaningful if this role plans
            if Phase.PLAN not in self.phases:
                self.state = State.FAILED
                break
            self.replans += 1
            if self.replans > self.max_replans:
                self.state = State.ESCALATED
                self._e("escalate", replans=self.replans)
                break
            self._e("replan", n=self.replans)
            self.state = State.REPLANNING
            self.plan = self._plan(msg)

        if self.mem_cfg.get("write"):
            tenant, seat = msg.get("tenant", "default"), msg.get("seat", self.defn["id"])
            chunks = self.bundle.get("chunks", [])
            record = {"content": f"[{self.defn['id']}] {self.state.value} · {len(self.outputs)} outputs",
                      "cites": [c["id"] for c in chunks], "category": "run"}
            ack = self.mem.write(tenant, seat, record)
            self.mem.consolidate(tenant, seat)          # STM->LTM hook (stub body, real call)
            self._e("memory_write", cites=record["cites"], status=ack.get("status"))
        self._e("run_end", state=self.state.value, replans=self.replans)
        return self._result()

    def _plan(self, msg):
        self.state = State.PLANNING
        self._e("plan_start")
        prompt = self.defn["planner"] + "\nINPUT:" + json.dumps(msg, sort_keys=True)
        plan = self.model.call("plan", prompt)
        self._e("plan_end", tasks=[t["task_id"] for t in plan["tasks"]])
        return plan

    def _implicit_plan(self, msg):
        # executor-family: no planner model call, no plan artifact tax.
        tool = (self.defn["frontmatter"].get("tools") or [None])[0]
        return {"plan_version": "v1", "plan_id": "implicit", "neop": self.defn["id"],
                "tasks": [{"task_id": "t1", "description": "direct execute",
                           "depends_on": [], "tool": tool, "acceptance": "tool returns",
                           "scope": "tool"}], "max_replans": 0, "_implicit": True}

    @staticmethod
    def _topo_order(tasks):
        """Order tasks so every task runs after its depends_on. Stable (preserves
        listed order among independents). Raises on cycle. (P2 DAG executor.)"""
        by_id = {t["task_id"]: t for t in tasks}
        order, done, temp = [], set(), set()

        def visit(tid):
            if tid in done:
                return
            if tid in temp:
                raise RuntimeError(f"cycle in plan at task '{tid}'")
            temp.add(tid)
            for dep in by_id[tid].get("depends_on", []):
                if dep in by_id:
                    visit(dep)
            temp.discard(tid)
            done.add(tid)
            order.append(by_id[tid])

        for t in tasks:
            visit(t["task_id"])
        return order

    def _execute_and_maybe_verify(self, plan, msg):
        self.outputs = {}
        for task in self._topo_order(plan["tasks"]):
            self.state = State.EXECUTING
            tool = task.get("tool")
            if tool:
                self._e("tool_call", task=task["task_id"], tool=tool)
                # thread upstream outputs into this task's input scope, keyed by dep task_id
                scope = {"text": msg.get("text")}
                for dep in task.get("depends_on", []):
                    scope[dep] = self.outputs.get(dep)
                out = self.tools.invoke(tool, scope)
                if isinstance(out, dict) and out.get("_blocked"):
                    self._e("tool_blocked", task=task["task_id"], tool=tool, reason=out["reason"])
                    self.state = State.FAILED
                    return False
                self.outputs[task["task_id"]] = out
                self._e("tool_result", task=task["task_id"], tool=tool, out=out)

            if Phase.VERIFY in self.phases:
                self.state = State.VERIFYING
                self._e("verify_start", task=task["task_id"])
                vprompt = (self.defn["verifier"] + "\nTASK:" + json.dumps(task, sort_keys=True)
                           + "\nOUT:" + json.dumps(self.outputs.get(task["task_id"]), sort_keys=True)
                           + "\nINPUT:" + json.dumps(msg, sort_keys=True))
                verdict = self.model.call("verify", vprompt)
                self._e("verify_end", task=task["task_id"], verdict=verdict)
                if not verdict.get("pass"):
                    return False
        return True

    def _result(self):
        return {"state": self.state.value, "plan": self.plan, "outputs": self.outputs,
                "tool_calls": self.tools.calls, "replans": self.replans,
                "phases": [p.value for p in self.phases], "events": self.events,
                "memory": {"retrieved": [c["id"] for c in self.bundle.get("chunks", [])],
                           "written": getattr(self.mem, "writes", []),
                           "consolidations": getattr(self.mem, "consolidations", [])},
                "total_ms": round((time.time() - self.t0) * 1000)}


# ============================================================ dispatch
def dispatch(folder, msg, mode, cassette, mocks, stm, memory=None):
    defn, diags = load_neop(folder)
    if defn is None:
        return {"state": State.REJECTED.value, "diagnostics": diags,
                "events": [], "tool_calls": []}
    agent = PiAgent(defn, ModelBroker(mode, cassette),
                    ToolBroker(mode, mocks, defn["tools"]),
                    MemoryBroker(mode, stm, bundle=memory))
    res = agent.run(msg)
    res["diagnostics"] = diags  # warnings surface even on success
    return res
