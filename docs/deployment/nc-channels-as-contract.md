# nc-channels ↔ Synapse — Application-Service contract conformance (A2 spike)

> **Purpose (work-order A2).** The AS↔Synapse contract was *spec-derived but never confirmed end-to-end*.
> This is that confirmation: each Matrix Application-Service API requirement mapped to the nc-channels code
> that satisfies it **and the test that proves it** — so the untraced risk is collapsed *before* live wiring.
> **Offline-provable today; the HTTP transport + live CS-API are box-gated** (named at the bottom, not faked).

**Verified state (2026-07-01):** `nc_channels` suite **46/46 green** (`test_matrix_adapter` 23 ·
`test_service` 15 · `test_registration` 8). The bridge is *built and tested* — the remaining Matrix work is
**prove (this doc) + wire (live, post-M1b)**, NOT build-from-scratch.

## The contract, point by point (spec → code → proof)

| # | Matrix AS-API requirement | nc-channels code | Test that proves it |
|---|---|---|---|
| 1 | **Registration** the HS loads — `id`, `url`, `as_token`, `hs_token`, `sender_localpart`, `namespaces` | `registration.py` `registration_dict` / `registration_yaml` | `test_registration_dict_has_all_required_spec_fields` |
| 2 | NEop **users namespace is `exclusive`** (M_EXCLUSIVE — only this AS mints `@neop_*`) | `registration.py` (`exclusive: true`) + `validate_registration_dict` | `test_neop_user_namespace_is_exclusive`, `test_validate_rejects_non_exclusive_users_namespace` |
| 3 | Secrets (`as_token`/`hs_token`) never embedded/committed | `validate_registration_dict` token-leak check | `test_validate_rejects_tokens_leaked_into_id`, `test_refuses_without_both_tokens` |
| 4 | **Inbound auth** — HS presents `hs_token` (Bearer; legacy `?access_token=`); AS rejects if absent/wrong | `service.py` `verify_hs_token` (constant-time), `bearer_from_headers` | `test_verify_hs_token`, `test_bearer_from_headers_prefers_authorization`, `test_bearer_legacy_query_fallback` |
| 5 | **At-least-once delivery** — duplicate `txnId` is a no-op (still 200), never reprocessed | `service.py` `process_transaction` (`_seen_txns`) | `test_transaction_dedup_is_idempotent` |
| 6 | **Event filtering** — route real human messages; skip own-puppet echo, non-message, edits-on-ingest | `matrix_adapter.py` `is_routable_message`; `service.process_transaction` | `test_process_transaction_maps_routable_events`, `test_process_transaction_skips_own_echo`, `test_mixed_transaction_counts_skips` |
| 7 | **Normalize** event → gateway `raw` (canonical envelope + CA-4 HMAC) for `orchestrator.handle` | `matrix_adapter.py` `matrix_message_to_raw`, `mint_adapter_hmac` | `test_raw_has_required_gateway_fields`, `test_raw_passes_gateway_authenticate`, `test_event_round_trips_through_orchestrator_handle` |
| 8 | **Outbound puppet** — act as `@neop_*` via `?user_id=` with `as_token` Bearer; mxid MUST be inside the exclusive namespace | `service.py` `reply_send` (namespace enforce → `OutboundSend`) | `test_reply_send_puppet_within_namespace`, `test_reply_send_puppet_outside_namespace_rejected`, `test_reply_send_builds_cs_api_descriptor` |
| 9 | **One AS per tenant** (CA-5) | `ASService.__init__` guards | `test_service_requires_tenant`, `test_service_requires_hs_token` |
| 10 | Full inbound→handle→outbound plan | `service.process_transaction` → `handle` → `reply_send` | `test_transaction_to_reply_round_trip` |

**⇒ Every offline-provable element of the AS↔Synapse contract is confirmed and test-backed.** The contract
is not a hypothesis anymore.

## Box-gated residue (named, not faked)
These need a reachable Synapse and stay box-gated — proven at live wiring, not here:
- **HTTP transport** — `service.serve` maps the contract onto `PUT /_matrix/app/v1/transactions/{txnId}`
  (→ 200 `{}`), `403` on bad `hs_token`, and the path routing. The *logic* it serves is tested above; the
  HTTP binding raises `NotImplementedError` until run on the box (`test_live_wire_is_box_gated`).
- **Outbound CS-API** — `service._cs_api_call` performs the actual `PUT .../send/...` with `Authorization:
  Bearer <as_token>`. The descriptor it sends (`OutboundSend`) is built + tested offline; the call is box-gated.

## What this de-risks
At the deploy step you (1) generate the registration with `registration_yaml(...)`, (2) point Synapse's
`app_service_config_files` at it, (3) register the AS on `matrix.neuraledge.in`. Because the contract is
confirmed offline, the only unknowns left at that step are *transport* (does the HTTP wiring run) — not
*contract* (does nc-channels speak AS correctly). That's the spike's whole job: shrink the live unknown to
transport, before spending the box-session on it.
