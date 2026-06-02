# NEOS

An ecosystem of **NEops** — Pi-style agents that run a typed runtime contract.
The phase set is a **function of `role_family`**, not fixed:

```
meta / sales / research : plan → execute → verify
reactive                : execute → verify
executor                : execute            (no plan, no verify tax)
```

`runtime/core.py` is the **executable spec** and the permanent test runtime behind
`nrt`. Production **Hermes** (Node) implements the same contract. Naming: Hermes =
host; a Pi-agent = a running NEop session; planner/executor/verifier = Pi-subagents.

### Pi-informed design (each earns its keep via `nrt`/ACP, not model hand-holding)
1. **Diagnostics-as-data** — the loader collects *all* defects (errors + warnings),
   never throws on first. `nrt validate` renders them.
2. **Typed event stream** — one `events[]` union (`run_start`, `plan_*`, `tool_call`,
   `tool_blocked`, `verify_*`, `run_end`, …) powers `nrt trace`, assertions, future UI.
3. **Runtime allowlist enforcement** — a non-declared tool returns a *blocked result*
   + emits `tool_blocked` and fails the run, in prod — not merely a CI assertion.
4. **Phase set per `role_family`** — a pure executor skips plan+verify entirely.

## Layout

```
runtime/core.py        Phase/State machine, diagnostics loader, brokers, PiAgent, dispatch()
runtime/aws.py         Read-only boto3 tool registry (live integration-mode AWS tools)
nrt/cli.py             NEOS Runtime Tester (validate | test | trace | suite | golden)
agents/<id>/
  neop.md              Frontmatter (neop_id, version, limits, role_family, tools, model, acp) + role prose
  tools.json           Tool universe; frontmatter `tools:` must be a SUBSET (allowlist)
  planner.md/verifier.md   Optional subagent prompts (warned if absent for a phase the role runs)
  fixtures/
    eval.jsonl         Cases: {case_id, input:{text}, expect:{terminal_state, expected_phases,
                              golden_plan, must_call_tools, must_not_call_tools, max_replans, ...}}
    golden_plan.json   Structural plan asserted against (task set + dep edges + tool assignment)
    mocks/tools.json   Tool mocks; {"$reflect_field":"text"} echoes an input field
    cassettes/<case>.json  Recorded model outputs, keyed <phase>:<sha256(prompt)[:16]>
```

## NEops

- **echo** (`role_family: meta`) — hello-world; full plan→execute→verify.
- **ping** (`role_family: executor`) — pure executor; `[execute]` only, no model calls.
- **aws-probe** (`role_family: executor`) — read-only AWS; calls `sts_whoami`, publishes caller identity.
- **recon** (`role_family: sales`) — first real-work NEop; 3-task DAG `search_leads → enrich_lead → dedupe`
  with `depends_on` edges, output threaded forward. Exercises the DAG executor and bounded-replan path.

## Mock keying (P2 decision)

Tool mocks are keyed by **tool name**. This held for Recon's 3-task DAG: each tool is
called once (and in the escalate path `search_leads` is called 3× but always wants the
same output, so no collision). Args-hash keying (`tool+sha(args)`) is **deferred** until a
real fan-out plan calls one tool many times with different args (e.g. enrich-per-lead) —
decided on pressure, not speculatively.

## AWS

AWS is wired into the **tool layer**, following the same mock-vs-live discipline as
models. `runtime/aws.py` is a lazy, credential-gated, **read-only** boto3 registry
(`sts_whoami`, `s3_list_buckets`, `dynamodb_list_tables`); profile/region come from
the standard AWS env. A NEop declares the AWS tools it needs in `tools.json`
(allowlist), tests them deterministically with `fixtures/mocks`, and — in
integration mode — the ToolBroker resolves them through `runtime.aws.run(name, args)`.
No mutating AWS tools ship without an explicit, reviewed addition.

## Run

```bash
python3 nrt/cli.py validate agents/echo
python3 nrt/cli.py test     agents/echo
python3 nrt/cli.py trace    agents/ping --case ping_basic   # typed event stream
python3 nrt/cli.py suite    agents                         # CI entrypoint: every NEop
```

## Test modes

- **unit** (default): deterministic. Model calls replay from cassettes (single-entry
  "bootstrap tolerance"); tools resolve from mocks. No network, no LLM, no key.
- **integration**: live model with recorded cassettes — `nrt golden --record` (next increment).

## Status

- **Step 1 — done.** Runtime contract + `echo` green under `nrt`.
- **Step 2 — done.** v2 refactor: diagnostics-as-data, typed event stream, runtime
  allowlist enforcement, `role_family`-driven phase sets; `ping` executor NEop added.
- **AWS — done.** Read-only boto3 tool registry + `aws-probe` NEop.
- **P2 (Recon) — done.** DAG executor (topo order by `depends_on` + output threading);
  `recon` sales NEop; happy→DONE and replan-exhaustion→ESCALATED green. Deferred: the
  recover-via-replan fixture (DONE via REPLANNING) needs per-attempt cassette keys —
  that's the `nrt golden --record` increment, not bootstrap-tolerance.
- P3 — real MemoryBroker over MemPalace (unit=recorded bundles / integration=live) +
  consumer NEop. Trace MemPalace surface first.
