# nc-channels transport + deploy design (2026-07-01)

> **Scope.** Converts "gap 3" (from `element-first-contact-runbook.md`) from *four unmade decisions* into a
> **precise box build-target**. This is DESIGN, not implementation — `service.py:119/125` (`serve` /
> `_cs_api_call`) **stay `NotImplementedError`**, and `test_service.py:131 test_live_wire_is_box_gated`
> **stays green**. The transport is built and proven *at the box, against real Synapse*, in one motion —
> never offline against a mock (that would be conformance-to-mock on the exact component whose correctness
> lives in the live handshake: the hollow-green trap). This doc gives the box a blueprint so that motion is
> mechanical, not exploratory.

## Decisions recorded (all four resolved)

| # | Decision | Resolution | Why |
|---|---|---|---|
| **D1** | De-stub `serve()`/`_cs_api_call` offline? | **NO — hold the gate. Spec only.** | Their correctness is defined by the live Synapse handshake (CS-API patterns, token exchange, txn/ack). An offline test-client encodes *our assumptions* about Synapse; a green proves match-to-mock, not match-to-Synapse — worst exactly where it matters. The team's `test_live_wire_is_box_gated` is a deliberate fence. Respect it. |
| **D2** | Co-location: runtime-task sidecar vs separate ECS service? | **Separate ECS service.** | The V1 spec names nc-channels as its own service; keeps the security-sensitive transport's failure domain *off* the execution runtime; independent scaling. "One less HTTP hop" is a weak reason to couple a transport into the runtime. |
| **D3** | Synapse reachability (gap 2)? | **In-VPC / bastion for alpha. Public ingress is a later, deliberate, post-pen-test call.** | Internal 5-seat alpha needs no public homeserver; keep Synapse off the internet until hardened. Public ingress is opened on purpose for external users, not for first-contact convenience. (Pen-test is a Day-90 gate.) |
| **D4** | Server name (gap 1)? | **In-VPC-resolvable now, forward-compatible with a real domain later.** Downstream of D3. | With D3 = in-VPC, the `.local`/internal name is fine for alpha; if D3 later flips to public it must become a real owned domain (`matrix.<domain>`). Pick a name that doesn't have to change if only the *exposure* changes. |

## 3b — the transport contract (box build target; stubs stay raising)
The offline-tested core already exists; the box build is **"wrap the proven core in HTTP,"** not design from
scratch. Reuse: `verify_hs_token` (`:68`), `bearer_from_headers` (`:74`), `process_transaction` (`:86`),
`reply_send` (`:103`). Pick a **minimal/stdlib HTTP server** (e.g. `http.server`) over a framework — smaller
container surface = less to jail (defense-in-depth). The contract is framework-agnostic:

### Inbound — `serve(host, port)` → one route
`PUT /_matrix/app/v1/transactions/{txnId}`:
1. `token = bearer_from_headers(headers, query)`; if `not verify_hs_token(token)` → **403** `{errcode:"M_FORBIDDEN"}`. (Constant-time; legacy `?access_token=` already handled.)
2. Parse JSON body (`{events:[...]}`).
3. `res = process_transaction(txnId, body)`. If `res.deduped` → **200 `{}`** immediately (at-least-once: a repeated `txnId` is a no-op). **Note:** `process_transaction` *maps only* — despite its docstring it does **not** call `handle`. `serve()` drives the seam over `res.processed`.
4. For each `raw` in `res.processed`:
   - `result = handle(raw, classifier, mode="live", rate=..., now_s=...)` — the orchestrator seam (`frontdoor/orchestrator.py:77`).
   - `room_id = raw["conversation_id"]` (= the event's room — set at `matrix_adapter.py:105`; also in `raw["metadata"]["room_id"]`). The reply routes here.
   - `puppet_localpart` = the seat's `@neop_*` (the NEop answering). `reply_send` enforces it's inside the exclusive namespace (`:110`) or raises before any live call.
   - `send = reply_send(room_id, result, out_txn_id, puppet_localpart=...)` with a **fresh unique `out_txn_id`** (send idempotency key).
   - `_cs_api_call(send)`.
5. **200 `{}`** on success (spec: ack the whole transaction once delivered/queued).

### Outbound — `_cs_api_call(send: OutboundSend)`
Execute the descriptor `reply_send` already built (`:113`): `PUT {send.path}` with `?{send.query}` (incl.
`user_id=@neop_*` for puppet) and JSON `send.body`, header `Authorization: Bearer <as_token>`. The
`OutboundSend` (path/query/body) is offline-tested; only the live PUT is new at the box.

### Open build-detail the box must NOT discover live (named here)
- **`out_txn_id` generation** — fresh per send (uuid). Idempotency key; don't reuse the inbound `txnId`.
- **Seat → `puppet_localpart` resolution — ✅ RESOLVED (no live guessing; derives from `handle()`'s output).**
  The answering `@neop_*` is **not** a room-state lookup or a separate seat-map — it falls straight out of the
  orchestrator result. `handle()` returns `result["neop"]` = the routed NEop (`orchestrator.py:105`,
  `run_seat`). So `serve()` resolves the reply per raw as:
  - `result = handle(raw, classifier, mode="live", ...)`.
  - **`result["type"] == "response"`** → `puppet_localpart = "neop_" + result["neop"]` (e.g. routed `echo` →
    `@neop_echo:<server_name>`); `reply_send(room_id, result, out_txn_id, puppet_localpart=...)` — which
    **already** rejects any mxid outside the exclusive `@neop_.*` namespace (`service.py:110`) before a live
    call, so a bad name fails closed, not on the HS. Sanitize `result["neop"]` to the localpart charset first.
  - **`result["type"] ∈ {disambiguate, refuse, error}`** → reply **as the AS sender** (`@<sender_localpart>`,
    the `@neos-bot`), **no puppet** — a system message (the decision's `question`/`reason`). These carry no
    `result["neop"]` to puppet, and shouldn't: a routing refusal speaks as the bot, not as a NEop.
  - `room_id = raw["conversation_id"]` (`matrix_adapter.py:105`). The room↔seat scope is already keyed in
    `handle` via the human's mxid → `(tenant, requester)`; the puppet is the *routed NEop*, not the human.
  ⇒ the "seat-map" this doc worried about doesn't need to exist for v1 — the mapping is `neop_<routed-neop>`,
    computed from data `handle()` already returns. (nc-web / multi-NEop rooms may later add explicit binding.)
- **`mode`/`rate`/`now_s`** — `serve()` calls `handle` with `mode="live"` (not "unit"); wire a real clock + rate limiter.

## 3a — the nc-channels ECS service (box build target, per D2 = separate service)
Modeled on the runtime service (`ecs.tf`) + Synapse (`synapse.tf`); **not written as TF yet** — it points at
`serve()`, which raises until 3b is built, so writing it now would deploy a crash-looping task. Shape:
- **Task def** `${name}-nc-channels`: image `var.nc_channels_image` (new var, like `synapse_image`); command runs `serve()`; `containerPort` = the AS port (e.g. 8010).
- **Secrets** (from Secrets Manager, never in TF state): `AS_TOKEN`, `HS_TOKEN`, `ADAPTER_HMAC_KEY` — see 3c bootstrap. Non-secret env: tenant, `server_name`, orchestrator/palace endpoints.
- **SG** `${name}-nc-channels-sg`: ingress on the AS port **from the Synapse SG only** (the HS PUTs transactions in-VPC); egress to the orchestrator + palace.
- **Cloud Map** `nc-channels.<ns>:port` — this is the `url` baked into the AS registration (what Synapse PUTs to). In-VPC only (D3).
- **Service** gated `count = enable_comms_tier ? 1 : 0`; private subnets; `assign_public_ip = false`.

## 3c — AS registration delivery + token bootstrap (box/secrets-gated — no offline mechanism)
The hard ordering, named so the box runs it as a checklist, not a discovery:
1. **Mint tokens** — generate `as_token`/`hs_token` (high-entropy), store in Secrets Manager. **Both sides must match**: the bridge reads them as secrets (3a) AND they appear in the registration file Synapse loads.
2. **Config delivery is NOT a TF line** — `matrixdotorg/synapse` *generates* `/data/homeserver.yaml` from env on first boot (EFS at `/data`). There is no `app_service_config_files` and no injection mechanism today. Box options: pre-seed `/data` with a homeserver.yaml that includes `app_service_config_files: [/data/nc-channels.yaml]` + write `registration_yaml(...)` to that path; or a conf.d/entrypoint hook. Pick one at the box.
3. **Chicken-and-egg** — the bridge needs Synapse to trust it (registration loaded) and Synapse needs the registration file (with tokens) before it'll route. Order: tokens → registration file on EFS → homeserver.yaml references it → restart Synapse → start the bridge → create bot/seat/room → first contact.

## The live window — one mutation at a time (ordering; the anti-circular sequence)

M1b, the comms-tier deploy, and the live-wire build are **no longer separable** — `_cs_api_call` has no
offline definition, so it can only be built with deployed comms + a live runtime + a real Synapse all on the
table at once. That makes the *order inside the one session* the whole game. The trap: the nc-channels ECS
service (3a) can't deploy until `serve()` stops raising, but `serve()` is what you're building against the
Synapse that service is meant to reach — deploy-the-service-first is circular. The way out is **box-process
first (prove the handshake by hand), ECS service second (make it durable)** — never both live at once, or a
first-contact failure has two possible owners (transport vs task health) and you're back to the July-1
two-variables-at-once thrash. Run this as a checklist, verifying each step before the next:

0. `[PRE-FLIGHT, offline — done]` G-A server_name baked (`matrix.neuraledge.in`, immutable); nc-channels ECS
   TF authored + HELD (`enable_nc_channels=false`); reachability path chosen (runbook §In-session reachability).
1. `[DEPLOY]` `terraform apply -var-file=phase2.tfvars` — comms tier up (Synapse + RDS + EFS + Redis + NATS).
   **`enable_nc_channels` stays false** — the AS service does NOT come up yet.
2. `[VERIFY]` Synapse healthy **with the right server_name** — exec/logs confirm `matrix.neuraledge.in`
   baked (this is the irreversible byte; catch a wrong one here, before rooms exist, not after).
3. `[DEPLOY]` AS registration + tokens (3c): mint `as_token`/`hs_token` → registration YAML on EFS →
   `homeserver.yaml app_service_config_files` → restart Synapse. Create `@neos-bot` + a seat room.
4. `[BOX-PROCESS]` **hand-drive `_cs_api_call` against the live Synapse** — a script run by hand (not an ECS
   task), iterating the CS-API PUT until a puppet `@neop_*` message actually lands in the room. This is where
   the live handshake is proven; owns exactly one variable.
5. `[BOX]` **wrap the proven call in `serve()`** — de-stub `service.py:119/125`, run the HTTP server locally
   against Synapse, confirm the full inbound-txn → handle → reply round-trip by hand.
6. `[DEPLOY]` **NOW flip `enable_nc_channels=true` and apply** — the transport is proven, so the ECS task
   comes up serving, not crash-looping. `nc-channels.<ns>:8010` matches the registration `url`.
7. `[LIVE]` Element first contact (runbook steps 5–6) — the round-trip now runs through the durable service.

Each `[VERIFY]` gate is a stop: a wrong server_name (step 2) or a failing hand-handshake (step 4) is caught
*before* the step that would make it expensive to undo.

## Net
Gap 3 is **box-gated almost in its entirety.** The offline work that remained was *design* (this doc), not
*implementation* — and it's done: `serve()` is **specified** (D1, gate held), co-location **decided** (D2 =
separate service), topology **chosen** (D3 = in-VPC), server-name **set** (D4 = forward-compatible). The
box-session now walks into gap 3 with a blueprint, not four open questions — the same conversion the runbook
did for first-contact. Nothing was built; no gate was crossed; no mock-green entered the record.
