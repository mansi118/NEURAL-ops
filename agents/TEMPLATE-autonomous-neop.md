# TEMPLATE — autonomous NEop (`pattern: agent`)

Copy this into `agents/<neop_id>/neop.md` and fill the placeholders. This is NOT discovered as a NEop
(discovery globs `agents/*/neop.md`; this is a loose reference file). It is the canonical shape the
linter (`runtime/neop_spec.py`) and `AGENT_PATTERNS.md` describe. **Only use `pattern: agent` when the
task is genuinely open-ended** — if the decomposition is fixed, it is a `workflow`, not an agent.

```yaml
---
neop_id: <id>
version: 1
pattern: agent                 # G1 — declared, and genuinely open-ended (not a pre-wired chain)
role_family: meta              # meta|sales|research → plan → execute → verify (G3: runs VERIFY)
model: { planner: <m>, executor: <m>, verifier: <m> }
limits:
  max_replans: 2               # G2 — HARD iteration cap; runtime → ESCALATED when exhausted (stop/escalate)
  phase_timeout_s: { plan: 10, execute: 20, verify: 10 }
memory: { read: true, write: false }   # augmented LLM: PALACE memory (palace_search/_remember via the shim)
twin: { read: true }
tools: [<tool_a>, <tool_b>]    # G5 — each must exist in tools.json with docstring-grade docs + poka-yoke args
acp: { publishes: [<output>] }
checkpoint: human              # G2/G4 — human gate before any irreversible / client-serving effect
---
# <Title> NEop  (pattern: agent)

WHY AGENT (justify the autonomy — required): <the task is open-ended because …>. The autonomy lives in
the DECOMPOSITION (the Planner chooses the sub-steps from THIS input), not in a fixed chain. If you
cannot justify open-endedness, downgrade to `workflow`.

LOOP (the gates, made concrete):
  - Augmented LLM: tools via the Tool Bus/MCP + memory via CORTEX-PALACE; no new store.
  - Planner → Executor → Verifier, bounded by max_replans (G2 stop/escalate).
  - G3 — the Verifier reads tool/execution results (ground truth from the environment) EACH step to
    assess progress and decide continue / replan / escalate — not only a final pass.
  - G6 — emit the Planner's decomposition and the plan to the typed event stream (transparency); not
    only tool calls + results. Keeps the agent auditable during the fail-open ACL window (T4 audit_tap).
  - checkpoint: a human gate before any irreversible or client-serving action.
```

Reference: `agents/AGENT_PATTERNS.md`. Conformance: `runtime/neop_spec.py` (G1–G3, G5-soft) + review (G4, G6).
