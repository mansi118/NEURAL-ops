# GAP-1 — port the `/mcp` contract into Hermes `memory.ts` (port spec + acceptance)

> **Scope.** Shrinks GAP-1 (`ADR-neop-runtime.md:111`) from an exploration into a checklist walk — the same
> move PR #71 did for the Matrix live-wire, aimed at the actual critical-path seam. GAP-1 = replace the
> `throw "live PALACE retrieval not wired"` in `pi-neop-runtime/src/brokers/memory.ts:23` with the proven
> `/mcp` contract, so Hermes memory reads/writes real CORTEX-PALACE under the seat's baked scope.
>
> **Provenance (the checklist's own honesty rule applies here):**
> - **Source contract — `✅⟨S⟩` verified this session** at `neop_jcode_adapter/palace_mcp_shim.py` (lines
>   cited inline). This is the thing being ported *from*; it is proven + unit-tested.
> - **Destination — `📄⟨ADR⟩→re-confirm`.** `memory.ts:23` (the throw), `model.ts:123-142` (requires
>   `ANTHROPIC_API_KEY`) are from the 2026-06-30 ADR about a repo **not opened this session.**
>   **STEP ZERO of GAP-1 is re-tracing `pi-neop-runtime` at file:line** — confirm the throw is still there and
>   the line hasn't moved *before* porting. If it drifted, that is "flag the ADR evidence as stale," not
>   "re-decide the runtime" (see the checklist's Two-Epistemic-Weights rule).
>
> **The trap this spec pre-writes the escape for:** the port is new surface (Python→TS) against a live index
> the runtime has never spoken to — the exact position #30's fusion was in when the offline green lied.
> match-to-shim ≠ match-to-live-Convex. So this spec defines GAP-1's **acceptance**, not just its
> implementation — Part 3 is the half that matters.

---

## Part 1 — The ported contract (mechanical; transcribe, don't design)
Port the **pure security core** `PalaceShim.build_request` (`palace_mcp_shim.py:224-243`) into `memory.ts`.
Same envelope, same header, same posture — a transcription:

**Scope (baked from env at construction, NEVER from the model / tool args):**
- `PALACE_MCP_URL`, `PALACE_ID` (palaceId), `NEOP_ID` (neopId) — read once at broker init. (`:26-29`)
- `.convex.site/mcp` endpoint (HTTP actions on `.site`, not `.cloud`). (`:27`)

**Request envelope** (`:232-238`) — the verified `/mcp` shape, NOT `{**args,...}`:
```
POST {PALACE_MCP_URL}
body    = { "tool": <name>, "palaceId": <PALACE_ID>, "neopId": <NEOP_ID>, "params": <toolArgs> }
headers = { "Content-Type": "application/json", "X-Palace-Neop": <NEOP_ID> }
```
**Allowlist** (`:57-59`): `palace_search`, `palace_remember` only; `palace_get_closet` gated OFF unless
`PALACE_ENABLE_GET_CLOSET` (Mempalace T8). Tool not on the list → reject (do not forward). (`:225-226`)

**Scope-spoof rejection** (`:61-64`, `:228-230`): if the tool args contain any of
`{palaceId, neopId, tool, params}`, **reject loudly** (raise), don't silently drop — spoof attempts must be
visible to the audit tap.

**Result classification** (`:269-277`): `allowed = httpStatus == 200 && resp.status == "ok"`. `403` → denied
at the Convex SoT (ACL); anything else non-ok → palace error. **Audit DENY as well as ALLOW** (`:251-252`) —
an allow-only log can't prove "zero isolation violations."

**Ed25519 signing** (`:239-242`) — forward-looking (Gate D not verified server-side yet): if
`PALACE_SIGNING_KEY_REF` resolves a key, add `X-NEop-Signature` (sign over canonical JSON — `sort_keys`, no
whitespace, `:146-148`) + `X-NEop-Pubkey`. Optional for GAP-1 green; port the hook, key can come later.

## Part 2 — The fail-closed invariant (PORTED, not reinvented — the seam inside the seam)
The shim is fail-closed **by construction** (`:201-217`). A Node/TS reimplementation is exactly where
fail-closed silently becomes fail-**open** — a `catch` that returns `[]`, an auth failure that degrades to an
unscoped read. **Port the invariant; do not re-derive a convenience.**

**Refuse to construct the broker** (mirror `ScopeNotConfigured`, `:201-214`) if:
- `PALACE_ID` / `NEOP_ID` / `PALACE_MCP_URL` is blank → **throw.** (Blank `neopId` defaults to `_admin`
  server-side, which **bypasses all ACL** — CLAUDE.md invariant.)
- `NEOP_ID` or `PALACE_ID` ∈ `{_admin, _system}` (reserved privileged identities, `:70`) → **throw.** Closes
  the explicit-misconfig path (a baked+signed ACL-bypass channel).

**On every read/write, any failure DENIES and RAISES — it never returns empty and never returns unscoped:**
- non-200 / `status != "ok"` / 403 / network error / malformed response / missing scope → **throw**, audit
  DENY. **Never `return []`.**
- **Why this is load-bearing:** "returns empty on error" is byte-indistinguishable from "graceful empty," and
  the LIVE-SEAM LAW just declared graceful-empty a FAILURE. A fail-open port would **both** violate the
  security posture **and** disguise itself as the soft-pass Part 3 forbids. One bug, two catastrophes.
- **Invariant, stated for the reviewer:** *there is no code path in `memory.ts` that returns a value on
  error. Error ⇒ raise. Empty-because-nothing-matched is a real result and is judged by Part 3's bar, not by
  a catch.*

## Part 3 — Live acceptance proof (the half that earns the spec; graceful-empty = FAIL, written concrete)
**GAP-1 is NOT done when `memory.ts` compiles and returns a shape.** It is done when a live run on Hermes
against **real Convex** retrieves the right closet at the right rank — and a graceful empty is a **hard FAIL**,
not a pass. This is fresh-write recall against a live index the runtime has never spoken to (the #30 seam).
Run it against live Convex (`.convex.site/mcp`), never an offline scaffold.

### The concrete proof (seed → query → assert)
Scope: the test seat `(palaceId = PID_TEST, neopId = seat_gap1)`.

1. **Seed** — `palace_remember`, `params`:
   ```
   { "wingName": "projects",
     "content": "The founding seat's primary project codename is BLUEFERN, running in ap-south-1.",
     "category": "fact" }
   ```
   Assert: HTTP 200, `status == "ok"`, a closet id returned. (Write half of the seam.)

2. **Retrieve** — `palace_search`, `params`: `{ "query": "what is the seat's project codename?", "limit": 5 }`
   **PASS requires ALL of:**
   - **Rank 1** result is the BLUEFERN closet from step 1 (id match).
   - Its score is **above the adaptive retrieval floor** (#29 adaptive-floor; ranked-retrieval baseline 0.986
     per `embedder-as-built.md`) — a real embedding hit, not a degenerate match.
   - The result set is **non-empty**.
   **FAIL (GAP-1 stays OPEN) on ANY of:**
   - Empty result set — **`graceful-empty = FAIL`, held literally** (`embedder-as-built.md:18`). This is the
     dead-embedder / #30 failure mode; it does not get a soft pass.
   - Rank-1 is a different closet, or the BLUEFERN closet is absent from the top-`limit`.
   - The score is at/below the floor (retrieval fired but didn't really match).

3. **Scope-isolation assertion (proves the fail-closed port end-to-end).** From a *different* seat
   `(PID_TEST, seat_other)`, run the same `palace_search`. **PASS requires:** the BLUEFERN closet is **NOT**
   returned (scope-bake isolates seats). A cross-seat leak here = GAP-1 FAIL **and** a security finding — it
   means the baked `neopId` isn't actually scoping the read.

### Done-definition (all three, on the record)
- [ ] Write returns ok under baked scope (Part 1 envelope verified live).
- [ ] Query returns BLUEFERN at rank 1 above the floor; **empty-or-wrong = open** (Part 3 bar).
- [ ] Cross-seat query does **not** return it (Part 2 fail-closed invariant proven live).
Only then is GAP-1 green and M1b's memory child (child-2) flips RED→GREEN on Hermes.

---

## Net
Three parts: the **ported contract** (mechanical, exact from the shim), the **fail-closed invariant** (ported
not reinvented — any error denies and raises, never empty, never unscoped), the **live acceptance proof**
(seeded BLUEFERN fact, rank-1-above-floor, graceful-empty=FAIL, cross-seat isolation). Once
`pi-neop-runtime` is checked out, Part 1 is transcription; Part 2 is a review checklist; Part 3 is the box
run that actually closes the gap. The box window becomes a checklist walk — not an exploration — on the seam
that's on the real critical path. **Step zero remains: re-trace `memory.ts` before porting into it.**
