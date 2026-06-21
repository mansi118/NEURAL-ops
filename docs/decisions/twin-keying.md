# Decision — Twin keying: per-user, not per-NEop

**Status: ACCEPTED (B2).** The one twin-layer identity change. Same reviewed-spec discipline as
`awaiting-approval` — load-bearing edit to the frozen file. Wire in THIS change (not "A now, B2 later").

## Problem (traced, not assumed)
The twin is the model of *the person*. As-built it is keyed **per-NEop**, by deliberate design:
- Store key: `put_twin`/`get_twin` set `twin_id = f"{tenant}:{seat}"`; Convex `twins` indexed `by_palace_neop (palaceId, neopId)`.
- `frontdoor/orchestrator.py`: `run_seat = decision["neop"]` — *"run seat = the ROUTED NEop (its own memory/twin key); requester rides along as attribution only — never as the memory/twin key."*
- `frontdoor/gateway.py`: requester = the human, *"It is NOT the run seat."* · `acp/router.py`: *"B runs under its own seat; sender = requester."*

⇒ The Interviewer seeds the twin under `(tenant, "interviewer")`; every other NEop reads its own. The
interview never reaches the user's other NEops; Decision Shadow / fidelity measure the NEop, not the
person. The per-user `requester` already rides in every `msg` — it is simply not used as the twin key.

## Decision
1. **Twin keyed by the user (`requester`); working memory stays per-seat.** The twin models the person →
   per-user. Per-run `write`/`retrieve` is NEop scratch → unchanged (per-seat). **Do not expand this to
   per-user shared memory** — the product's "company brain" is the per-**tenant Vault** tier (P4 tiering,
   a separate, not-yet-live workstream), NOT per-user memory. This change touches the twin only.
2. **Twin access is identity-based self-access (B2), NOT memory-gated.** Reading/writing your own twin is
   *being who you are*, categorically different from `recall`/`remember` (memory of stored facts). Gating
   own-twin access behind a memory permission is a category error. B2 fixes the category: twin ops are
   ungated from `recall`/`remember`; authorization is "the twin whose key is your own server-derived
   identity." This (a) deletes the `binding ⇒ perms` footgun entirely (own-twin access is structural, no
   provisioning order to get wrong, no silent-deny class), and (b) avoids B1's over-grant — B1 would hand
   every human seat general memory `recall`+`remember` just to unlock twin access, conflating identity with
   memory; B2 keeps a seat able to reach its self-model while its memory rights stay scoped.
3. **Spec-first, then wire** (this doc). Confirmed → wire → tests.

## The rule
```
# core.py — the ONLY behavioural change. Backward-compatible: no requester ⇒ twin_owner == seat ⇒ identical.
twin_owner = msg.get("requester") or seat
# assemble (twin read):   self.mem.get_twin(tenant, twin_owner)      # was: get_twin(tenant, seat)
# _finalize (twin write): self.mem.put_twin(tenant, twin_owner, draft)   # was: put_twin(tenant, seat, draft)
```
`runtime/memory.py` get_twin/put_twin signatures are unchanged — we pass `twin_owner` as the seat arg, so
the live `/mcp` twin op carries `neopId = requester`. Memory ops keep passing `seat`. No Convex code change
(see §2 below). Scope of edit: ~3 lines in `core.py`, at the twin read + twin write only.

## The three points that keep it correct (pinned)

### 1. Security linchpin — the twin key uses the SERVER-DERIVED requester, never a caller-supplied value
A per-NEop twin could not leak across users; a per-*user* twin could, **iff `requester` were forgeable** (a
NEop running for A asserting `requester=B` reads B's twin). It is not: `acp/edge_auth.py` (E1–E5) mints
`requester` from the AS-verified `mxid` → `resolve_binding` seat_id, **overwrite-or-refuse, never from the
body**. So a NEop can only ever key its real requester's twin. **Invariant (must hold): `twin_owner`
derives only from the server-side `requester`; a model/body-supplied requester is never trusted.** This
change is safe *because of* the edge-auth work already shipped — that is its precondition.

### 2. Convex twin ACL — B2 carve-out: twin ops are ungated from memory perms, authorized by identity
Traced: `convex/palace/twins.ts` `getTwin`/`putTwin` do **no** `assertNeopScope` — they query `twins` by
`(palaceId, neopId)` with an exact `q.eq("neopId", neopId)`; `neopId = body.neopId ?? header ?? "_admin"`
(broker-supplied today; Gate D deferred). The only gate is `runtimeOpForTool` → `enforceRuntimeOp(perms,
recall|remember)` — a *memory* capability check, the category error B2 fixes.

**The B2 change:** remove `palace_get_twin`/`palace_put_twin` from `TOOL_TO_OP` so twin ops are NOT gated by
`recall`/`remember`. A twin op can only ever touch the twin at its own request `neopId` (no cross-key
addressing exists), so every twin access is own-twin self-access — authorized by *being* that identity.

**The carve-out's single safety bar (write precisely):** "own twin" = an **exact** match on the
server-derived identity — the twin op keys by `q.eq("neopId", neopId)` where `neopId` is the server-minted
requester. **No prefix, no wildcard, nothing looser.** This adds **no new trust assumption**: it rests on
the same edge-auth invariant the whole keying already rests on (point 1 — `requester` is unforgeable). It
just removes a memory-permission check that never provided cross-user isolation anyway (isolation comes
from `neopId` being server-derived + exact-keyed, not from the `recall`/`remember` gate).

This **deletes** caveat (a) from the prior draft: no `neop_permissions` row is needed to reach your own
twin, so there is no `binding ⇒ perms` dependency and no silent-deny footgun.
- **(b) Gate D forward-intersection still holds.** When S0.3 signed-identity lands and the server derives
  `neopId` server-side, twin ops must derive the **requester**, not the executing NEop (twin neopId =
  requester; memory neopId = seat). The exact-match bar above is what S0.3 must preserve.
- **Cleanup trace (RESOLVED 2026-06-21 — no-op):** traced whether seat provisioning grants human seats
  `recall`+`remember` to make A-style twin access work. **It does not — nothing to remove.**
  `upsertSeatBinding` (`convex/access/bindings.ts`) writes only the `seat_bindings` row, never
  `neop_permissions`. The only perms-granting paths are `setNeopPermissions` (`palace/mutations.ts`,
  admin-driven, arbitrary ops) and the `DEFAULT_NEOP_PERMS` provision template (`palace/provision.ts` —
  `_admin` + NEop seats at palace setup). No path grants a human/user seat `recall`+`remember` for twin
  access. ⇒ There was never an over-grant, because there was never an A-style workaround: `binding ⇏ perms`,
  so A would have **silently denied** the first real user their own twin. This is the third independent
  confirmation (alongside §1 the throw, §2 the missing perms row) that going structural (B2) was correct.

### 3. The twin-touching meta-NEops must carry the user — not fall through to `or seat`
The **Twin Curator** evolves the user's twin; the **Decision Shadow** predicts the user. Both are
user-*about*, not user-*less*. If either runs as a background trigger with no `requester`, the `or seat`
fallback keys it to the NEop's own twin — the Curator would write to *itself*. **Their dispatch must thread
the target user as `requester`/`twin_owner` even when triggered.** The `or seat` fallback is correct only
for genuinely user-less system runs.

## Acceptance (offline)
- **Regression:** no `requester` ⇒ byte-identical (every current fixture/agent green; the wrapper smokes run
  seatless-of-requester → `twin_owner == seat` → unchanged).
- **New:** two distinct NEops dispatched with the **same** `requester` read the **same** twin (per-user
  shared). · Interviewer with `requester=U` writes the twin at `(tenant, U)`. · Twin Curator triggered with
  `requester=U` curates `(tenant, U)`, not `(tenant, "twin-curator")`. · A forged body `requester` is
  ignored (edge-auth precondition asserted at the seam, not re-checked in core).
- **Convex (when live):** confirm a member/human seat with recall+remember can `palace_get_twin` /
  `palace_put_twin` at its own requester key (perm-gate passes) — caveat 2(a).

## Diff scope (B2, this change)
- **`core.py` (NEURAL-ops):** the `twin_owner = msg.get("requester") or seat` line + its use at the twin
  read (assemble) and twin write (`_finalize`). ~3 lines. Backward-compatible (no requester ⇒ unchanged).
- **Convex (Mempalace):** remove `palace_get_twin`/`palace_put_twin` from `TOOL_TO_OP` (the B2 carve-out)
  + a comment documenting twin = identity self-access, exact `neopId` match, no memory perm. + vitest:
  a seat WITHOUT recall/remember can still get/put its OWN twin; the op only touches its own `neopId` key.
- **Meta-NEop dispatch (point 3):** Twin Curator + Decision Shadow must thread the target user as
  `requester` even on background triggers — documented in their `neop.md`; the `or seat` fallback is for
  genuinely user-less system runs only.
- **No seat-provisioning change** (B2 removed that need). Cleanup trace is post-wire, not part of the diff.
