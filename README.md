# NEOS

An ecosystem of **NEops** — Pi-style agents that run a typed runtime contract:

```
load → assemble → plan → execute → verify → DONE
```

`runtime/core.py` is the **executable spec** and the permanent test runtime behind `nrt`.
Production **Hermes** (Node) implements the same contract. Naming: Hermes = host;
a Pi-agent = a running NEop session; planner/executor/verifier = Pi-subagents.

## Layout

```
runtime/core.py        State machine, loader, brokers (Model/Tool/Memory), PiAgent, dispatch()
tools/nrt.py           NEOS Runtime Tester (validate | test | trace | suite | golden)
neops/<id>/
  neop.md              Frontmatter (neop_id, version, limits, tools, model roles, acp) + role prose
  tools.json           Tool universe; frontmatter `tools:` must be a SUBSET of this (allowlist)
  fixtures/
    eval.jsonl         Cases: {case_id, input:{text}, expect:{terminal_state, golden_plan, must_call_tools, ...}}
    golden_plan.json   Structural plan asserted against (task set + dep edges + tool assignment)
    mocks/tools.json   Tool mocks; {"$reflect_field":"text"} echoes an input field
    cassettes/<case>.json  Recorded model outputs, keyed <phase>:<sha256(prompt)[:16]>
```

## Run

```bash
python3 tools/nrt.py validate neops/echo      # frontmatter + allowlist subset check
python3 tools/nrt.py test     neops/echo      # run all fixtures (unit mode, deterministic)
python3 tools/nrt.py trace    neops/echo --case echo_hello   # per-phase trace
python3 tools/nrt.py suite    neops            # CI entrypoint: every NEop
```

## Test modes

- **unit** (default): deterministic. Model calls resolve from cassettes (with single-entry
  "bootstrap tolerance"); tools resolve from mocks. No network, no LLM.
- **integration**: live model with recorded cassettes — `nrt golden --record` (next increment).

## Status

- **Step 1 — done.** Runtime skeleton + `echo` hello-world NEop green under `nrt`
  (happy path `DONE`; allowlist enforcement `FAILED` a non-declared tool).
- Step 2 — real planner/executor/verifier roles behind the stub seam + cassette record/replay.
- Step 3 — ACP (`publishes`/`subscribes`) so NEops compose into a graph.
- Step 4 — more NEops + `role_family`-driven phase config (executor-only NEops skip plan/verify).
