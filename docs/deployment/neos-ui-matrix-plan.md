# NEOS UI / Matrix plan — verified-true (2026-07-01)

> **Reconciled from chat → repo.** This plan lived only in chat; a trace proved its Status labels stale
> (nc-channels was called the *unbuilt keystone* — it is in fact **built and offline-green**). This is the
> verified version. **Framing shift (read this, not just the checkboxes): the remaining Matrix work is
> `prove + wire`, NOT `build the adapter from scratch`.** First contact via Element is *nearer* than the old
> plan read.

## Keystone insight (unchanged, and now realised)
You don't choose "UI or Matrix." **`nc-channels` is a Matrix Application-Service bridge — and `nc-web` and
Element are both just Matrix clients on the same rooms.** Land the bridge → Element works immediately (zero
build, your instant test surface) while `nc-web` (the product UI) builds in parallel. The bridge is the
keystone, and **the keystone is built.**

## Verified status (over the stale labels)
| Piece | Old label | **Verified-true** |
|---|---|---|
| `nc-channels` adapter + service | "unbuilt keystone" | **BUILT + green** — `matrix_adapter.py` + `service.py`, suite **46/46** |
| AS registration (the file the HS loads) | (missing) | **BUILT** — `registration.py` generator + validator (8 tests) |
| AS↔Synapse contract | "spec-derived, never run" | **CONFIRMED offline** — `docs/deployment/nc-channels-as-contract.md` (every requirement → code → test) |
| Element first-contact | "to build" | **zero build** — stock Matrix client on the seat room, once the bridge is live |
| `nc-web` (Slack-shape client) | "to build" | genuinely **unbuilt** — the product UI; `[LIVE]`, builds post-M1b on a proven base |
| Live wiring (HS loads reg · transaction round-trip) | — | `[BOX]`/`[LIVE]` — `service.serve` + `_cs_api_call`, box-gated |

## The honest split
- **The Matrix *build* is essentially done offline.** Adapter, service, registration, and the contract
  confirmation are all green. There is **no offline Matrix artifact left to build** before the box.
- **The Matrix *live test* is box-gated.** It talks to a running runtime + a reachable Synapse — both behind
  the box-session. There is no frontend path around it.

## Live-and-test sequence (where each step's gate sits)
1. `[OFFLINE ✓ done]` adapter + service + **registration** + **AS-contract confirmation**.
2. `[BOX — your authorization]` the box-session → M1b (deploy `Mempalace#29`, GAP-1 + GAP-2 proofs).
3. `[BOX/deploy — your gate]` the "Phase-2.5" delta: Synapse you already run (`matrix.neuraledge.in`) +
   Redis + NATS + `nc-channels` + ALB; point `app_service_config_files` at `registration_yaml(...)`.
4. `[deploy]` register the AS + create the `@neos-bot` + `@neop_*` puppet users + a seat room.
5. `[LIVE]` **test through Matrix:** open Element → log into a seat → chat. Round-trips
   `nc-channels → orchestrator.handle → runtime → streams back`. **That's "test through Matrix"; Element is
   the first-contact UI.**
6. `[LIVE, parallel]` `nc-web` — the Slack-shape client on the same rooms + the dashboard on the app-plane.
   **That's "test through a UI" — the product surface; it must not gate first contact.**

## Bottom line
The keystone is built and its contract is confirmed; first contact = **box-session → register the AS →
Element**, with `nc-web` following in parallel. The only lever left is the **box-session** (steps 2–3, yours);
everything offline is done.
