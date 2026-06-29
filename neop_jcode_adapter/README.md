# neop_jcode_adapter

Run a NEop's inner loop on **jcode** behind the NEOS runtime contract. NEOS keeps identity, ACL,
audit, events, transport; jcode owns only the per-seat agent loop. **jcode is configured, never
forked.** Spec: [`../docs/neop-jcode-adapter-implementation-plan.md`](../docs/neop-jcode-adapter-implementation-plan.md).
Invariants + verified corrections: repo-root [`../CLAUDE.md`](../CLAUDE.md).

## Status (2026-06-29)

| Task | Component | State |
|---|---|---|
| **T0** | spike — live round-trip | **BOX-GATED** (needs jcode binary + `ANTHROPIC_API_KEY` + live palace + Docker). Go/no-go before T1 integration. |
| **T1** | `palace_mcp_shim` | ✅ **built + unit-green (19/19)** — scope-lock, allowlist, fail-closed, signing. |
| T2 | `config_render` | ✅ **built + green** — to jcode's real schema (provider `anthropic-api`, `$JCODE_HOME/{config.toml,mcp.json}`, tiers→`[tools].disabled`). Class A renders **tight (worker posture) until `jail_enforced=True`** — config + sandbox go live together. |
| T2 | `isolation` | stub (box-gated — Docker; carries the jail `config_render` Class A waits on) |
| T3 | `supervisor` | stub (box-gated) |
| T4 | `audit_tap` + `event_bridge` | ✅ **built + green** — pre-S0 jsonl/local-log fallback; jsonl line IS the canonical ClickHouse row (who·when·what·on-whom·permission·result·`denied_at_layer` + scope); taps **allow AND deny** (shim refusals + 403s); **non-fatal + log-on-drop**; metadata-only (no payloads/secrets); `sink` hook for the NATS/ClickHouse cutover |
| **T5** | `safety_policy` + `pre_tool_hook` | ✅ **built + green** — matrix (pure data) → `[tools].disabled` (T2) **plus the dynamic ask/allow gate** as jcode's `[hooks].pre_tool` (contract traced from jcode@master: tool in `JCODE_HOOK_TOOL_NAME`, exit 0=allow/2=block, **anything-else FAILS OPEN** → the hook is fail-closed in its own logic). Policy **baked per-seat** (`NEOP_SEAT_CLASS`/`SWARM_ENABLED`/`JAIL_ENFORCED`), never from the model. Enforces the B/C swarm divergence (grant-gated). Jail (T2) stays the real boundary. |
| **T6** | `memory_promoter` | ✅ **built + green** — parses the real `jcode memory export --scope all` shape (traced: a flat JSON **array of MemoryEntry**, `category` bare-string \| `{"custom":…}`, includes superseded `active:false` → dropped). Export is durable-only by construction (no durable Session scope) so ephemeral chatter never appears. Promotes live entries via `palace_remember` **through the shim** (injected `writer` seam → pure/offline-testable; `make_shim_writer` for prod). Best-effort: a single write failure never aborts the batch. |
| — | `seat_classes` | ✅ presets built (pure data) |

**All offline-buildable components are now built + green.** What remains is box-exec only: the Docker
jail (`isolation._docker_run` / `supervisor._spawn`), running `jcode`, and the **T0 go/no-go spike** —
the exact replay recipe is in [`docs/deployment/jcode-t0-spike-runbook.md`](../docs/deployment/jcode-t0-spike-runbook.md)
(STOP-and-show), then the **T7 red-team** gate before any client data.

## The shim is the tenant chokepoint

One `palace_mcp_shim` process == one seat. It exposes only `palace_search` / `palace_remember`
(`palace_get_closet` gated until Mempalace T8) and forwards to the live `/mcp` with `(palaceId,
neopId)` **baked from env, never from the model**.

**What actually enforces isolation in v1** (the `/mcp` endpoint does **not** verify signatures yet —
Gate D deferred to S0.3; a missing scope defaults to `_admin` and bypasses ACL):
1. scope injected from env; model-supplied scope/envelope keys rejected 100%;
2. **fail-closed**: the shim refuses to start on blank `PALACE_ID`/`NEOP_ID`;
3. the container egress jail (T2).

Ed25519 signing is implemented and tested but is **forward-looking defense-in-depth** — it becomes a
real trust boundary only when Layer 2 verification ships.

## Test

```bash
python3 -m pytest neop_jcode_adapter/tests/ -q
```
