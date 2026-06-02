---
neop_id: interviewer
version: 1
role_family: meta
model: { planner: stub, executor: stub, verifier: stub }
limits: { max_replans: 1 }
memory: { read: true, write: false }
twin: { read: true, write: true }      # twin-lifecycle NEop: seeds the twin
tools: [draft_twin]
acp: { publishes: [twin] }
---
# Interviewer NEop
Onboarding NEop (Flow 1). Conducts a bounded interview (a recorded transcript in unit
mode) and drafts a schema-valid `twin.md` **v0** (`maturity: seed`) for the seat, written
through the MemoryBroker (`put_twin`) on `run_end`. The fidelity clock and Twin Curator
are P-later — this produces the seed only.
