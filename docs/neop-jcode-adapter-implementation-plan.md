# NEop ⟷ jcode Harness — Implementation Plan

> **Status:** Build-ready handoff · **Owner:** ML · **Confidentiality:** CONFIDENTIAL — INTERNAL (NeuralEDGE)
> **Repos touched:** `NEURAL-ops` (primary, Python) · `Mempalace_NEOS` (one optional Convex/TS task)
> **Target runtime:** AWS `ap-south-1` (t4g/Graviton, aarch64) + Mac mini (Colima)
> **Purpose:** A spec precise enough that a Claude Code agent can implement it directly. Implementation-level choices may remain; design-level ambiguity should not.

> **NOTE (2026-06-18):** Three of the §1 invariants were traced against the live repos and refined.
> See `CLAUDE.md` → "VERIFIED REALITY" for the corrections (signatures are not verified server-side
> yet; the real `/mcp` body shape; `palace_get_closet` query exists but is not an MCP tool). Build to
> those.

---

## 0. What you're building

A thin **`neop-jcode-adapter`** (Python package in `NEURAL-ops`) that lets a NEop run its inner agent loop on **jcode** (`1jehuang/jcode`, the Rust coding-agent harness) **behind the existing NEOS runtime contract**. NEOS keeps owning identity, ACL, audit, events, and transport. jcode owns only the per-seat agent loop. **jcode is configured, never forked.**

**v1 scope: NeuralEDGE-tenant seats only.** No client data on a jcode seat until the isolation + audit gates (T7) pass red-team.

The adapter makes each jcode process a single-tenant unit and wraps it so it satisfies what NEOS requires that jcode doesn't natively provide: `tenant+seat` scoping, ACL inheritance, audit, events, and palace-backed memory.

---

## 1. Ground truth — invariants Claude Code must not violate

These are facts about the live stack. Do not invent architecture around them; a needed-but-missing piece is a **blocker to surface**, not an assumption to code past.

1. **Memory is CORTEX-PALACE only.** Reached by HTTP POST to `/mcp` with `palace_search` + `palace_remember`, scoped by `palaceId` (tenant) + `neopId` (seat). Embeddings are server-side. Never stand up a new store.
2. **`palace_get_closet` (by-id fetch) does not exist yet** in `Mempalace_NEOS` — it has search + write only. Twin-style by-id retrieval is blocked until T8 ships it. Respect the twin **by-id-only** invariant.
3. **The 4-layer ACL is currently fail-open.** The fail-open→fail-closed SoT flip is deferred to **S0.3**. Until then, **the OS/container jail carries the isolation guarantee, not the ACL.** Design accordingly — do not rely on ACL fail-closed behavior that isn't live.
   - Layers: (1) Convex SoT, (2) FalkorDB bridge w/ Ed25519-signed headers, (3) MCP tool wrapper, (4) Python SDK call-site.
4. **jcode is Rust; the spine is Python.** The adapter is a Python supervisor that *manages* jcode processes — it does not link into jcode. jcode is driven via its CLI/server, config files, and MCP config.
5. **Bedrock is blocked account-wide** on the mansi-synlex account (400 ValidationException, not permissions). jcode uses a direct **`ANTHROPIC_API_KEY`**, which bypasses Bedrock entirely. Inject per seat.
6. **`runtime/memory.py` stays embedding-agnostic** and gates only on `CONVEX_DEPLOYMENT_URL`. Don't couple the adapter to a specific embedder.

---

## 2. Repos & where code lands

### `NEURAL-ops` (primary — Python)
```
neural-ops/
└── neop_jcode_adapter/
    ├── __init__.py
    ├── supervisor.py          # SeatSupervisor: lifecycle for per-seat jcode processes
    ├── isolation.py           # IsolationUnit: container/namespace + JCODE_HOME jail + egress policy
    ├── config_render.py       # ConfigRenderer: per-seat config.toml + .jcode/mcp.json + safety policy
    ├── palace_mcp_shim.py     # stdio MCP server → authenticated HTTP /mcp (the tenant chokepoint)
    ├── audit_tap.py           # AuditTap: palace ops + transcript → NATS → ClickHouse (local-jsonl fallback)
    ├── event_bridge.py        # EventBridge: NEop lifecycle/significant events → NATS
    ├── safety_policy.py        # SafetyPolicy: render jcode safety-system tiers per seat
    ├── memory_promoter.py     # MemoryPromoter: session-end promotion of jcode local graph → palace
    ├── seat_classes.py         # Class A / B / C policy presets
    └── tests/
```

### `Mempalace_NEOS` (Convex/TS — **one optional task, T8**)
```
mempalace_neos/convex/
└── palace.ts                  # add palace_get_closet(palaceId, neopId, id) + MCP tool registration + ACL wrapper
```
Only build T8 if a Class A/B pilot needs twin-style by-id fetch. Otherwise defer.

---

## 3. Component contracts

Signatures are the contract; implementation choices (async runtime, container lib) are yours.

### 3.1 `palace_mcp_shim` — the tenant chokepoint (most security-critical)
A small **stdio MCP server** that jcode launches via its command-based `mcp.json`. It forwards the allowlisted palace tools to the HTTP `/mcp` endpoint, **with `palaceId`/`neopId` baked in from env (never accepted from the model)** and **Ed25519-signed headers**. Because the scope is fixed per process and signed here, a seat's jcode process cannot escape its tenant even with the ACL fail-open.

```python
ALLOWED_TOOLS = {"palace_search", "palace_remember", "palace_get_closet"}  # get_closet gated on T8

# env (injected per seat by ConfigRenderer):
#   PALACE_MCP_URL, PALACE_ID, NEOP_ID, PALACE_SIGNING_KEY_REF  (keyref → secret store, never plaintext)

async def handle_tool_call(name: str, args: dict) -> dict:
    if name not in ALLOWED_TOOLS:
        raise ToolRejected(name)
    if "palaceId" in args or "neopId" in args:       # model must NOT set scope
        raise ScopeSpoofRejected()
    body = {**args, "palaceId": PALACE_ID, "neopId": NEOP_ID}
    headers = ed25519_sign(body, key=load_key(PALACE_SIGNING_KEY_REF))
    resp = await http_post(PALACE_MCP_URL, json=body, headers=headers)
    await audit_tap.emit(seat=(PALACE_ID, NEOP_ID), tool=name, args=args, result_meta=summarize(resp))
    return resp
```
> Build correction (traced): the real `/mcp` body is `{"tool": name, "palaceId": PALACE_ID,
> "neopId": NEOP_ID, "params": args}` + header `X-Palace-Neop: NEOP_ID`. Signatures are not verified
> server-side yet (Gate D deferred) — sign anyway (forward-looking), but the enforced guarantees are
> env-baked scope + fail-closed-on-blank + the egress jail.

### 3.2 `ConfigRenderer`
Renders an isolated jcode home per seat. Use a per-seat `JCODE_HOME` so config, creds, and the local memory graph never share state across seats.

Per-seat `config.toml`:
```toml
[provider]
default_provider = "claude"
default_model = "<pin a Claude model id>"

[providers.claude]
type = "anthropic"
api_key_env = "ANTHROPIC_API_KEY"   # per-seat key injected into the jailed process env
```

Per-seat `.jcode/mcp.json` (points only at the shim — jcode never sees the raw palace URL or signing key):
```json
{
  "servers": {
    "cortex-palace": {
      "command": "python",
      "args": ["-m", "neop_jcode_adapter.palace_mcp_shim"],
      "env": {
        "PALACE_MCP_URL": "<palace /mcp url>",
        "PALACE_ID": "<tenant>",
        "NEOP_ID": "<seat>",
        "PALACE_SIGNING_KEY_REF": "<keyref>"
      },
      "shared": false
    }
  }
}
```

### 3.3 `IsolationUnit`
One container per `(palaceId, neopId)`. v1: Docker (plain on EC2; inside Colima on the Mac mini). Per seat: isolated `JCODE_HOME`, a jailed working dir, **no host filesystem access**, and **egress restricted to the palace endpoint + the Anthropic API only**. The container boundary is the tenant boundary while ACL is fail-open.

```python
class IsolationUnit:
    def launch(self, seat: SeatId, image: str, env: dict, workdir_mount: str) -> Handle: ...
    def egress_allowlist(self) -> list[str]:  # palace host + api.anthropic.com only
        ...
```

### 3.4 `SeatSupervisor`
```python
class SeatSupervisor:
    def start(self, seat: SeatId, cls: SeatClass) -> Handle: ...   # spawns jailed jcode (server mode)
    def stop(self, seat: SeatId) -> None: ...
    def status(self, seat: SeatId) -> SeatStatus: ...
    def run_once(self, seat: SeatId, prompt: str) -> RunResult: ... # wraps `jcode run`
    # crash → restart with backoff; resumes session if jcode supports it for that seat
```

### 3.5 `SafetyPolicy` → jcode safety-system tiers
Render jcode's action classes per seat class. Map every non-palace tool surface to a tier:

| Tool surface | Class B / C (workers, build) | Class A (NeP lab) |
|---|---|---|
| `palace_*` via shim | auto-allowed | auto-allowed |
| raw shell / filesystem (host) | **always-denied** | jailed sandbox only |
| browser | always-denied (unless task needs it → permission) | denied |
| self-dev / self-modify | **always-denied** | allowed **in throwaway sandbox only** |
| swarm spawn | permission-required | auto-allowed (within sandbox) |

### 3.6 `AuditTap` + `EventBridge`
- **AuditTap:** every palace op (from the shim) → NATS subject → ClickHouse. On session end, export the jcode transcript. **Fallback:** if NATS/ClickHouse aren't deployed (pre-S0), write an append-only `audit/*.jsonl` per seat and flip to NATS/ClickHouse when the substrate lands.
- **EventBridge:** publish NEop lifecycle (`started`/`stopped`/`crashed`/`promoted`) and significant events to NATS for the dashboard and other NEops.

### 3.7 `MemoryPromoter`
On session end, promote durable items from jcode's **ephemeral** local memory graph into the palace via `palace_remember` (scoped). The palace stays SoT; the local graph is a per-seat working cache. Mirrors the Vault Promoter pattern.

---

## 4. Build sequence (the sprint plan — Claude Code executes in order)

Each task: **goal · files · verify · done.** Tasks marked ⚡ can run as parallel swarm workers; the rest are sequential.

**T0 — Spike (no adapter).** Hand-run one jailed jcode process with a hand-written config + the shim. **Verify:** `jcode run "remember <fact>; then search <fact>"` round-trips through the shim to the palace and a row lands in Convex under the test scope. **Done:** round-trip + `ANTHROPIC_API_KEY` path both green. *(Go/no-go gate.)*

**T1 ⚡ — `palace_mcp_shim`.** **Files:** `palace_mcp_shim.py`, tests. **Verify (unit):** signing is valid; model-supplied `palaceId`/`neopId` is rejected 100%; non-allowlisted tool rejected. **Verify (integration):** search/remember against a test palace scope. **Done:** scope-lock + allowlist tests pass.

**T2 — `ConfigRenderer` + `IsolationUnit`.** **Verify:** two seats launch in separate containers with separate `JCODE_HOME`; neither can read the other's fs or memory; egress allowlist blocks a third host. **Done:** two isolated seats run concurrently.

**T3 — `SeatSupervisor`.** **Verify:** supervise 2 seats; kill one → it restarts with backoff; `status()` reflects state. **Done:** lifecycle API stable.

**T4 — `AuditTap` + `EventBridge`.** **Verify:** every palace op produces an audit row (or jsonl-fallback row pre-S0); lifecycle events land on the NATS subject; transcript exported on session end. **Done:** 100% palace-op audit coverage.

**T5 — `SafetyPolicy` hardening.** **Verify:** a Class B seat cannot shell out, read host fs, hit arbitrary egress, or self-modify. **Done:** all denied surfaces blocked in tests.

**T6 — `MemoryPromoter`.** **Verify:** durable memory from a session appears in the palace under the right scope; ephemeral chatter does not. **Done:** promotion correct + scoped.

**T7 — Red-team isolation suite (milestone-critical).** Attempt: cross-tenant read, `palaceId`/`neopId` spoof from the model, egress escape, fs escape, signing-key exfil. **Done:** **zero leakage across every vector.** *(Hard gate before any client data.)*

**T8 ⚡ (optional) — `palace_get_closet` in `Mempalace_NEOS`.** Only if a pilot needs by-id twin fetch. Add the Convex function + MCP tool registration + ACL wrapper, respecting by-id-only. **Done:** by-id fetch works under scope; shim allowlist updated.

**T9 — Class A pilot (NeP self-improvement lab).** Sandboxed self-dev loop improving one real NeP/skill against its metric, human-gated promotion. Natural target: graduate the email-composer loop into jcode-driven Stage 2 shadow mode. **Done:** measurable lift, 0 unreviewed changes reaching client-serving artifacts.

**T10 — Class B pilot (swarm batch).** Wire a recon/ALTE-enrichment NEop as coordinator + workers. **Done:** enrichment rounds/hr beat the measured serial baseline.

**T11 — Density + cost + 30-day soak.** Pack N seats per Graviton box; record RAM/seat and $/seat vs spine; run the T7 suite continuously for 30 days. **Done:** cost delta recorded; isolation clean over 30 days → folds into the 90-day milestone.

---

## 5. Acceptance tests (objective pass/fail)

**Pyramid:** unit (shim signing/scope-lock, safety tiers) → integration (seat ↔ palace, supervisor lifecycle) → E2E (a full NEop run on a jailed seat with audit + promotion).

| Criterion | Target |
|---|---|
| Cross-tenant reads (red-team) | **0** across all vectors, sustained 30 days |
| Model-supplied scope rejected | **100%** |
| Palace-op audit coverage | **100%** (NATS/ClickHouse or jsonl fallback) |
| Class A NeP lift | ≥ target on the NeP's own metric; **0** unreviewed client-serving changes |
| Class B throughput | enrichment rounds/hr **>** serial baseline (measure baseline first) |
| RAM/seat at N seats | record vs spine; target jcode's ~10 MB/added-session profile |

---

## 6. Guardrails (hard constraints for Claude Code)

- **Internal tenant only in v1.** No client data on a jcode seat until **T7 passes**.
- **Isolation rides on the container jail until ACL fail-closed lands at S0.3.** Don't weaken the jail on the assumption the ACL will catch leaks.
- **Self-dev is sandboxed and never runs against a client-serving binary or artifact.**
- **Every action is auditable or it doesn't ship.** No silent tool surfaces.
- **The shim is the only path to the palace.** jcode never holds the raw palace URL or signing key; scope is never model-supplied.

---

## 7. Pre-S0 dependency flags

These must exist for the tasks noted; if the substrate is pre-S0, use the degraded fallback and activate the real wiring when it lands.

| Dependency | Needed by | If absent (pre-S0) |
|---|---|---|
| Container runtime (Docker/Colima) | T2 | Single-host Docker on EC2 / inside Colima on Mac mini |
| NATS | T4 | Events to local log; flip to NATS later |
| ClickHouse (`nc-audit`) | T4, T7 | Append-only `audit/*.jsonl` per seat |
| Secret store for signing key | T1 | A locked-down env/keyref on a single host; **never plaintext in config** |

---

## 8. Open decisions for ML (resolve before/at T1)

1. **OpenClaw lineage.** If jcode's "OpenClaw" shares lineage with the NEOS runtime's OpenClaw/Hermes, the adapter gets meaningfully thinner — confirm before scoping. (Read jcode `docs/SERVER_ARCHITECTURE.md` + `docs/AMBIENT_MODE.md`.)
2. **`palace_get_closet` now or defer?** Build T8 up front only if a pilot needs twin by-id fetch.
3. **Container runtime.** Docker for v1 (recommended) → Firecracker as the harden-later option for stronger seat isolation.
4. **Anthropic key scoping.** Per-seat keys (clean usage attribution + blast-radius limiting, recommended) vs one org key.
5. **Pilot targets.** Class A: which NeP? (default: email-composer Stage 2.) Class B: recon vs ALTE enrichment?

---

## 9. Driving this with Claude Code

Drop `CLAUDE.md` at the `NEURAL-ops` repo root so the agent inherits the invariants and build order
(done — see the repo-root `CLAUDE.md`, which also carries the 2026-06-18 VERIFIED REALITY corrections).

Suggested command sequence:
1. `jcode` self-setup on the target box (use the repo's bootstrap prompt; prefer existing creds, then `ANTHROPIC_API_KEY`).
2. Point Claude Code at the plan: *"Implement T0, then stop and show me the round-trip result."*
3. After T0 green: *"Proceed through T1–T6 in order, running tests after each. Spawn a parallel worker for T1's shim tests if useful. Stop at T7."*
4. Run T7 yourself as the gate. Only after it's clean: authorize T9/T10 pilots.

**Swarm note:** jcode's own coordinator/worker swarm is what Class B (T10) *uses at runtime*; for *building* the adapter, T1 (shim) and T8 (Convex) are the cleanly independent units to parallelize.

---

*Build the adapter as the layer you run NEops on with jcode — not a replacement for the OpenClaw/Hermes spine. Internal seats prove it out; the spine keeps serving clients until the gates are green.*
