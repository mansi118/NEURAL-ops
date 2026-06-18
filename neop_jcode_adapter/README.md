# neop_jcode_adapter

Run a NEop's inner loop on **jcode** behind the NEOS runtime contract. NEOS keeps identity, ACL,
audit, events, transport; jcode owns only the per-seat agent loop. **jcode is configured, never
forked.** Spec: [`../docs/neop-jcode-adapter-implementation-plan.md`](../docs/neop-jcode-adapter-implementation-plan.md).
Invariants + verified corrections: repo-root [`../CLAUDE.md`](../CLAUDE.md).

## Status (2026-06-18)

| Task | Component | State |
|---|---|---|
| **T0** | spike — live round-trip | **BOX-GATED** (needs jcode binary + `ANTHROPIC_API_KEY` + live palace + Docker). Go/no-go before T1 integration. |
| **T1** | `palace_mcp_shim` | ✅ **built + unit-green (19/19)** — scope-lock, allowlist, fail-closed, signing. |
| T2 | `config_render` | ✅ **built + green (12 tests)** — to jcode's real schema (provider `anthropic-api`, `$JCODE_HOME/{config.toml,mcp.json}`, tiers→`[tools].disabled`) |
| T2 | `isolation` | stub (box-gated — Docker) |
| T3 | `supervisor` | stub (box-gated) |
| T4 | `audit_tap` + `event_bridge` | stub (shim already emits the jsonl audit fallback) |
| T5 | `safety_policy` | matrix built (pure data) + tests; jcode-dialect render in T2 |
| T6 | `memory_promoter` | stub (blocked on jcode local-graph export format) |
| — | `seat_classes` | ✅ presets built (pure data) |

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
