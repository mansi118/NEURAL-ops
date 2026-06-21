---
neop_id: twin-curator
version: 1
role_family: meta
pattern: workflow         # deterministic curation pass (corroborate -> maturity -> commit), not autonomous (G1)
model: { planner: stub, executor: stub, verifier: stub }
limits: { max_replans: 1 }
memory: { read: true, write: false }
twin: { read: true, write: true }      # twin-lifecycle NEop: curates the seat's twin
tools: [curate_twin]
acp: { publishes: [twin-curator] }
---
# Twin Curator NEop (Flow 8)

The meta-NEop that advances a seat's twin: apply only **corroborated** edits, recompute the fidelity
score, and advance the maturity machine (seed→growing→mature; drifted under override pressure). A
**workflow** — a fixed pipeline (gather signals+edits → corroborate → next_maturity → commit), not
dynamic autonomy.

Logic lives in `runtime/curator.py` (`curate`/`fidelity`/`corroborated`/`next_maturity`, pure + tested
in `tests/test_curator.py`). This NEop runs it on the plan→execute→verify contract so curation is an
auditable, twin-versioned NEop run. The live `curate_twin` tool binds to `runtime.curator.curate` and
returns the **curated twin** (its `twin` field — corroborated edits applied, maturity advanced); the
broker writes it back via `put_twin` on run end. The fixture mock mirrors that exact curated twin. An
edit commits only with enough field signals (T-6); versioning is the broker's (single-writer per twin).
