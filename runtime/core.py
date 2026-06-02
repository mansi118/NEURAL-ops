"""NEOS runtime core (reference / test-mode).

Loads a NEop folder, instantiates it as a Pi-agent, runs plan -> execute -> verify.
Production Hermes (Node) implements the SAME contract; this Python core is the
executable spec and the permanent test runtime behind `nrt`.

Naming: Hermes = host. Pi-agent = a running NEop session. planner/executor/verifier
= Pi-subagents. A "NEop run" is a Pi-agent session.
"""
from __future__ import annotations
import enum, json, time, hashlib, pathlib

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("pip install pyyaml")


# ----------------------------------------------------------------------------- state machine
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


# ----------------------------------------------------------------------------- loader
REQUIRED_FRONTMATTER = ["neop_id", "version", "limits"]


class LoadError(Exception):
    pass


def _split_frontmatter(text: str):
    if not text.startswith("---"):
        raise LoadError("missing frontmatter fence '---'")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise LoadError("malformed frontmatter")
    return yaml.safe_load(parts[1]) or {}, parts[2].strip()


def load_neop(folder) -> dict:
    """Resolve + validate a NEop folder. Fails LOUD on any defect (NR-2)."""
    folder = pathlib.Path(folder)
    neop_md = folder / "neop.md"
    if not neop_md.exists():
        raise LoadError(f"no neop.md in {folder}")
    fm, body = _split_frontmatter(neop_md.read_text())
    for k in REQUIRED_FRONTMATTER:
        if k not in fm:
            raise LoadError(f"frontmatter missing required key '{k}'")
    tools = []
    if (folder / "tools.json").exists():
        tools = json.loads((folder / "tools.json").read_text())
    declared = fm.get("tools", [])
    if not set(declared) <= set(tools):
        raise LoadError(f"frontmatter tools {declared} not a subset of tools.json {tools}")

    def read(name):
        p = folder / name
        return p.read_text() if p.exists() else ""

    return {
        "id": fm["neop_id"],
        "version": fm["version"],
        "frontmatter": fm,
        "role": body,
        "planner": read("planner.md"),
        "executor": read("executor.md"),
        "verifier": read("verifier.md"),
        "tools": tools,
        "folder": folder,
    }


# ----------------------------------------------------------------------------- brokers
def cassette_key(phase: str, prompt: str) -> str:
    """LOCKED recorded-stub key: <phase>:<sha256(prompt)[:16]>."""
    return f"{phase}:{hashlib.sha256(prompt.encode()).hexdigest()[:16]}"


class ModelBroker:
    """Routes a subagent call. unit mode = deterministic cassette lookup."""

    def __init__(self, mode: str, cassette: dict | None = None):
        self.mode = mode
        self.cassette = cassette or {}

    def call(self, phase: str, prompt: str):
        if self.mode != "unit":
            raise RuntimeError(f"mode '{self.mode}' not wired in the step-1 reference (unit only)")
        key = cassette_key(phase, prompt)
        if key in self.cassette:
            return self.cassette[key]
        # bootstrap tolerance: exactly one recorded entry for this phase
        cands = [v for k, v in self.cassette.items() if k.startswith(phase + ":")]
        if len(cands) == 1:
            return cands[0]
        raise RuntimeError(f"cassette miss for {key} — run `nrt golden --record` to capture it")


class ToolBroker:
    """Enforces the tools.json allowlist; serves mocks in unit/integration mode."""

    def __init__(self, mode: str, mocks: dict, allowlist):
        self.mode = mode
        self.mocks = mocks
        self.allowlist = set(allowlist)
        self.calls = []  # list of {"tool":, "allowed":}

    def invoke(self, tool: str, args: dict):
        allowed = tool in self.allowlist
        self.calls.append({"tool": tool, "allowed": allowed})
        if not allowed:
            raise PermissionError(f"tool '{tool}' not in allowlist {sorted(self.allowlist)}")
        if self.mode not in ("unit", "integration"):
            raise RuntimeError("live tools not wired in the step-1 reference")
        if tool not in self.mocks:
            raise RuntimeError(f"no mock for tool '{tool}' (add to fixtures/mocks)")
        m = self.mocks[tool]
        if isinstance(m, dict) and "$reflect_field" in m:  # echo a field of the input
            f = m["$reflect_field"]
            return {f: args.get(f)}
        return m


class MemoryBroker:
    """unit mode = fixture STM + no-op write sink (no external deps)."""

    def __init__(self, stm: list):
        self.stm = stm
        self.writes = []

    def retrieve(self, *_a, **_k):
        return {"chunks": [], "provenance": []}

    def write(self, rec):
        self.writes.append(rec)


# ----------------------------------------------------------------------------- Pi-agent
class PiAgent:
    """A running NEop session. Owns the plan -> execute -> verify loop."""

    def __init__(self, defn: dict, model: ModelBroker, tools: ToolBroker, memory: MemoryBroker):
        self.defn = defn
        self.model = model
        self.tools = tools
        self.mem = memory
        self.state = State.LOADING
        self.trace = []
        self.replans = 0
        self.max_replans = defn["frontmatter"]["limits"].get("max_replans", 2)
        self.plan = None
        self.outputs = {}
        self.t0 = time.time()

    def _emit(self, phase, **kw):
        self.trace.append({"phase": phase, "t_ms": round((time.time() - self.t0) * 1000), **kw})

    def run(self, msg: dict) -> dict:
        self.state = State.ASSEMBLING
        bundle = self.mem.retrieve(msg)
        self._emit("assemble", stm=len(self.mem.stm), bundle=len(bundle["chunks"]))

        self.plan = self._plan(msg)
        while True:
            ok = self._execute_and_verify(self.plan, msg)
            if ok:
                self.state = State.DONE
                break
            if self.state == State.FAILED:
                break
            self.replans += 1
            if self.replans > self.max_replans:
                self.state = State.ESCALATED
                self._emit("escalate", replans=self.replans)
                break
            self.state = State.REPLANNING
            self._emit("replan", n=self.replans)
            self.plan = self._plan(msg)
        return self._result()

    def _plan(self, msg):
        self.state = State.PLANNING
        prompt = self.defn["planner"] + "\nINPUT:" + json.dumps(msg, sort_keys=True)
        plan = self.model.call("plan", prompt)
        self._emit("plan", tasks=[t["task_id"] for t in plan["tasks"]])
        return plan

    def _execute_and_verify(self, plan, msg):
        self.outputs = {}
        for task in plan["tasks"]:  # step-1: linear walk; DAG topo-order is the next increment
            self.state = State.EXECUTING
            tool = task.get("tool")
            if tool:
                # side-effecting -> approval gate; auto-grant in test mode
                self.state = State.AWAITING_APPROVAL
                self.state = State.EXECUTING
                args = {"text": msg.get("text")}
                try:
                    out = self.tools.invoke(tool, args)
                except PermissionError as e:
                    self._emit("execute", task=task["task_id"], denied=str(e))
                    self.state = State.FAILED
                    return False
                self.outputs[task["task_id"]] = out
                self._emit("execute", task=task["task_id"], tool=tool, out=out)
            self.state = State.VERIFYING
            vprompt = (self.defn["verifier"] + "\nTASK:" + json.dumps(task, sort_keys=True)
                       + "\nOUT:" + json.dumps(self.outputs.get(task["task_id"]), sort_keys=True)
                       + "\nINPUT:" + json.dumps(msg, sort_keys=True))
            verdict = self.model.call("verify", vprompt)
            self._emit("verify", task=task["task_id"], verdict=verdict)
            if not verdict.get("pass"):
                return False
        return True

    def _result(self):
        return {
            "state": self.state.value,
            "plan": self.plan,
            "outputs": self.outputs,
            "tool_calls": self.tools.calls,
            "replans": self.replans,
            "trace": self.trace,
            "total_ms": round((time.time() - self.t0) * 1000),
        }


# ----------------------------------------------------------------------------- dispatch
def dispatch(folder, msg: dict, mode: str, cassette: dict, mocks: dict, stm: list) -> dict:
    """Runtime API entrypoint: load -> instantiate Pi-agent -> run."""
    try:
        defn = load_neop(folder)
    except LoadError as e:
        return {"state": State.REJECTED.value, "error": str(e), "trace": [], "tool_calls": []}
    agent = PiAgent(
        defn,
        ModelBroker(mode, cassette),
        ToolBroker(mode, mocks, defn["tools"]),
        MemoryBroker(stm),
    )
    return agent.run(msg)
