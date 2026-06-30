# NEOS — Matrix UI integration plan (2026-07-01)

> **Scope.** HOW the Matrix UI (Element first-contact + nc-web) integrates with the spine + backend once
> they're live. Complements `neos-ui-matrix-plan.md` (the strategic keystone view) and
> `nc-channels-as-contract.md` (the AS↔Synapse contract, confirmed offline). This doc is the wiring +
> deploy topology + gate-tagged sequence.
>
> **Readiness finding (read first):** the live spine is the **runtime tier only** — **Synapse is gated
> behind `enable_comms_tier`, currently `false`.** So Matrix integration depends on **two** gate events,
> both yours: (1) the **box-session → M1b** (backend proven live), and (2) the **comms-tier deploy**
> (Synapse/NATS/Redis up). The Matrix *build* is done; the *live integration* waits on those two.

## Architecture — two planes, one backend
```
 CHAT PLANE (Matrix bus)                                          APP PLANE (dashboard)
 Element / nc-web ──Matrix CS-API──► Synapse ──AS txn──► nc-channels        nc-web ──HTTPS──► gateway app-plane
   (a seat's room)                  (matrix.       (service.serve)             (fidelity · Decision Queue ·
        ▲                            neuraledge.in)      │ matrix_message_to_raw       memory peek · twin viewer)
        │ reply_send (puppet @neop_*)                    ▼
        └──────────────── Synapse ◄── nc-channels ◄── frontdoor.orchestrator.handle(raw, classifier)
                                                          │ dispatch
                                                          ▼
                                            Hermes NEop runtime (seat-serve, jailed)
                                                          │ /mcp (GAP-1)
                                                          ▼
                                            CORTEX-PALACE (Convex SoT + Titan embed + FalkorDB)
```
- **nc-web and Element are both just Matrix clients on the same seat rooms** — that's the keystone. Element
  needs zero build (first-contact); nc-web is the product surface + the app-plane dashboard.

## The wiring contracts (each already built/confirmed offline)
| Edge | Contract | Status |
|---|---|---|
| Synapse → nc-channels | AS registration (`registration.py`) loaded via `app_service_config_files`; HS pushes `PUT /_matrix/app/v1/transactions/{txnId}` (hs_token auth) | offline-confirmed (`nc-channels-as-contract.md`); HTTP serve box-gated |
| nc-channels → backend | `matrix_message_to_raw` → `frontdoor.orchestrator.handle(raw, classifier, mode=...)` | seam unit-green; adapter 46/46 |
| backend → Hermes | orchestrator dispatch → seat-serve (`serve --mode live`) | built; **M1b-proven on the box** |
| Hermes → palace | `/mcp` memory (GAP-1) + adaptive-floor retrieval (#29) | built; box-proven at M1b |
| nc-channels → Synapse | `reply_send` puppet (`@neop_*`, exclusive namespace) → CS-API `PUT .../send` w/ as_token | offline-confirmed; `_cs_api_call` box-gated |
| nc-web → app-plane | gateway HTTP for dashboard data | `[LIVE]` — built post-M1b |

## Deploy topology — the comms-tier delta (your gate)
The runtime tier is live. Matrix needs the comms tier (`enable_comms_tier=true`, `phase2.tfvars`), or a
"Phase-2.5" subset:
- **Synapse** (`synapse_image`) — reuse `matrix.neuraledge.in`; load the nc-channels AS registration.
- **NATS** (events) + **ElastiCache/Redis** (txn dedup / streaming) — per the comms tier.
- **nc-channels** service — serves the AS endpoint, binds to `frontdoor.orchestrator.handle` (co-located
  with the runtime or its own ECS service reaching the orchestrator).
- **ALB** route to nc-channels' AS endpoint so the HS can reach it.

## Gate-tagged integration sequence
1. `[OFFLINE ✅ done]` bridge (adapter+service+registration) + AS-contract confirmation + this plan.
2. `[BOX — your authorization]` box-session → **M1b**: deploy `Mempalace#29`, `gap1`+`gap2` proofs green,
   merge the 4, then your separate **T9** word. Backend is now live-proven.
3. `[DEPLOY — your gate]` comms-tier flip: stand up Synapse + NATS + Redis + nc-channels + ALB.
4. `[DEPLOY]` register the AS on `matrix.neuraledge.in` (`registration_yaml(...)` → `app_service_config_files`);
   create `@neos-bot` + `@neop_*` puppets + a seat room.
5. `[LIVE]` **Element first-contact:** log into a seat → chat → round-trips bridge → orchestrator → Hermes →
   palace → streams back. **This is "test through Matrix."**
6. `[LIVE, parallel]` nc-web: Matrix client on the same rooms (chat) + app-plane (dashboard). Must not gate
   first-contact (Element covers it).

## Bottom line
The Matrix UI **build** is complete and confirmed offline. The **integration** is good-to-go the moment its
two foundations are live — **M1b (box-session)** and **the comms-tier deploy (Synapse)** — both your gates,
neither build work. After step 2+3, steps 4–6 are bounded wiring on a proven base, with Element giving
first-contact immediately and nc-web following in parallel. No `[LIVE]` step is built ahead of `[BOX]`.
