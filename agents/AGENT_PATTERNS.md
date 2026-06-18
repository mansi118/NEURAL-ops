# Agent Patterns — the NEop build reference (enforced, not just understood)

Source: Anthropic, *Building Effective Agents*. This is the **neop-spec reference module**: every NEop
declares which pattern it is, and the conformance linter (`runtime/neop_spec.py`, run in CI via
`tests/test_neop_spec.py`) enforces the gates below at build time — so conformance is automatic, not
left to per-agent discretion. `core.py` is the runtime loader and stays byte-identical; this dimension
rides as an additive `pattern:` frontmatter key it ignores.

## Three principles (apply to every NEop)
1. **Simplicity first.** Use the simplest thing that works; add complexity (a loop, autonomy) only when
   it *demonstrably* improves outcomes. Most NEops are augmented calls or workflows, not agents.
2. **Transparency.** Show the planning steps. The orchestrator's *decomposition* and the NEop's *plan*
   must land in the typed event stream / audit (not only tool calls + results) — this also keeps the
   orchestrator auditable during the fail-open ACL window.
3. **ACI (Agent–Computer Interface).** Tool design carries ~equal weight to prompts: docstring-grade
   tool docs, example usage, and poka-yoke'd arguments (e.g. absolute paths) so the model can't misuse
   them. Ties to the jcode tool gating + the tool-resolution pipeline.

## The classification dimension (required `pattern:` in every neop.md)
| pattern | what it is | NEOS shape | declare when |
|---|---|---|---|
| `augmented_call` | one augmented LLM/tool call, no loop | `role_family: executor` (execute-only) | a single transform/lookup |
| `workflow` | a **predefined** code path orchestrating steps | prompt-chain / route / parallel / **pre-wired** orchestrator-workers | the control flow is fixed; autonomy (if any) is only in content |
| `agent` | LLM **dynamically directs its own process** + env feedback + stop condition | `plan → execute → verify → replan` (meta/sales/research) under a hard cap | the task is genuinely open-ended |

> **Don't default to autonomous.** A pre-wired chain is a *workflow* even if it strings several LLM
> calls together — the autonomy must live in the **decomposition**, nowhere else (see Orchestrator-
> workers). Calling a workflow an "agent" buys compounding-error risk and cost for no benefit.

## The seven patterns, mapped to NEOS
- **Augmented LLM** (the base block) — an LLM + retrieval + tools + memory behind a clean interface.
  *NEOS:* the NEop primitive — agent loop + Tool Bus/MCP + CORTEX-PALACE (`palace_search`/`palace_remember`).
- **Prompt chaining** *(workflow)* — fixed pipeline with intermediate checks. *NEOS:* the structured
  pipelines (Shift: Strategist→Writer→Image→QA; legal: NDA→…→Invoice) with human gates as the checks.
- **Routing** *(workflow)* — classify input → dispatch to the right handler / model tier. *NEOS:* the NC
  orchestrator's intent-classify → NEop dispatch (COC gates); cheap model for simple, capable for hard.
- **Parallelization** *(workflow)* — sectioning / voting. *NEOS:* TeamComs parallel dispatch, QC layers,
  classifier voting, COC guardrail-as-sectioning.
- **Orchestrator-workers** *(agent-grade)* — an orchestrator that **dynamically determines** subtasks
  from the input (NOT pre-defined) and delegates. *NEOS:* NC orchestrator → NEop workers + multi-NEop
  join; the ACP Recon→Researcher→Proposal chain. **The decomposition is the autonomy.** If a chain is
  pre-wired, it is prompt-chaining (`workflow`), and must be named that.
- **Evaluator-optimizer** *(agent-grade)* — generate → evaluate against feedback → refine. *NEOS:* the
  NeP self-improvement loop (Execute→NE-Eval→Learn→Rewrite), Decision Shadow (twin vs actual), the
  in-loop Verifier.
- **Autonomous agent** — a tool-using loop that plans, acts, and gains ground truth from the environment
  each step, with stopping conditions. *NEOS:* the autonomous NEop (Planner→Executor→Verifier). One-shot
  transforms are **not** agents.

## The six gates (enforced at spec time)
| # | gate | enforcement |
|---|---|---|
| G1 | **Classify every NEop** (augmented_call / workflow / agent); never default to autonomous. | linter — `pattern:` required + valid |
| G2 | **Autonomous NEops carry a hard iteration cap + stop/escalate.** | linter — `agent` ⇒ bounded `limits.max_replans` (runtime escalates when exhausted) |
| G3 | **The Verifier consumes environment feedback each step**, not only at the end. | linter — `agent` ⇒ role runs VERIFY; template puts tool/exec results into the verify loop |
| G4 | **Orchestrator-workers must be dynamic** — subtasks chosen from the input, else it's a workflow. | reference + review; the NC orchestrator codifies decompose→dispatch→synthesize |
| G5 | **ACI is a first-class artifact** — docstring-grade tool docs + poka-yoke'd args + a test pass. | linter (soft: tools resolve to `tools.json`) + reference |
| G6 | **Transparency** — the decomposition + plan land in the event stream / audit, not only tool calls. | reference + the autonomous template emits its plan to the stream; T4 `audit_tap` carries it |

G1–G3 + G5(soft) are linted now (`runtime/neop_spec.py`). G4/G6 are codified in the autonomous
template (`agents/TEMPLATE-autonomous-neop.md`) and the NC orchestrator; they are review gates until the
orchestrator decomposition + plan steps are asserted in the trace.

## The autonomous-NEop template
Canonical shape for a `pattern: agent` NEop — see **`agents/TEMPLATE-autonomous-neop.md`**:
augmented LLM (MCP tools + PALACE memory) → Planner→Executor→Verifier loop → **max-iter stop + human
checkpoint** → full plan/decomposition **trace to the event stream**.
