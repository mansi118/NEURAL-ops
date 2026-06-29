# nc-channels — trace + scoped build plan (the untraced surface, de-risked)

**Dated 2026-06-29.** Goal: convert "`nc-channels` ~1–2 wk, untraced" into a concrete subtask list with
the unknowns *named*, so "looks like a switch, is a gated spike" doesn't fire a third time. Parallelizable
with jcode T0 (off its critical path).

## Headline (the trace's main finding)
**The front-door LOGIC already exists and is unit-green** — `nc-channels` is a Matrix **transport adapter**
binding to it, not a front-door build. Verified by reading first-party code:
- `frontdoor/orchestrator.py` → `handle(raw, classifier, *, mode, rate, now_s, …)` does the FULL round-trip:
  `gateway.authenticate(raw)` → `gateway.normalize(raw)` → `resolve_identity` → rate-limit (GW-3) →
  `route` (classify/mention, COC-1/4) → `dispatch` → returns `{"type":"response","stream":[…tokens…], …}`.
- `frontdoor/gateway.py` → the inbound contract is **`raw`**: `REQUIRED_RAW=("channel","user_id","text")`
  + `token` + `hmac` (auth, CA-4); `user_id="tenant:requester"`; optional `msg_id, conversation_id,
  thread_id, attachments, mentions, ts, metadata`.
- Synapse homeserver is in `infra/terraform/synapse.tf` (RDS Postgres + EFS + ECS + Cloud Map) — **built,
  gated off** (`enable_comms_tier=false`); public client ingress (ALB host rule + TLS) is a noted activation step.

⇒ **The seam is `orchestrator.handle(raw, classifier, …)`.** nc-channels must (a) turn a Matrix event into
`raw`, call `handle`, and (b) turn the returned `stream` back into Matrix messages. That's the whole job.

## The two paths to build
**Inbound** (Matrix → NEop): Synapse pushes events to the AS via `PUT /_matrix/app/v1/transactions/{txnId}`
(authenticated by the `hs_token`). For each `m.room.message`: map → `raw = {channel:"matrix",
user_id:"<tenant>:<mxid-localpart>", text:body, conversation_id:room_id, thread_id:(rel), token:<as_token>,
hmac:<adapter-hmac CA-4>, ts, mentions, metadata}` → `orchestrator.handle(raw, classifier, mode="integration", …)`.

**Outbound** (NEop → Matrix): take `result["stream"]` → send to the room via the CS API
`PUT /_matrix/client/v3/rooms/{roomId}/send/m.room.message/{txn}` using the `as_token` (optionally
`?user_id=@neop_<id>:server` to puppet the NEop identity, within the AS namespace).

## Existing vs net-new
| Piece | State |
|---|---|
| envelope contract, gateway auth/normalize/resolve/rate-limit, route, dispatch, **stream_tokens** | ✅ built + unit-green |
| Synapse homeserver (RDS/EFS/ECS/CloudMap) | ✅ in TF, **gated off** |
| **AS adapter service** (txn ingest → raw → handle → CS send) | ✅ **BUILT 2026-06-29** — `nc_channels/service.py` (dedup, hs_token auth, map→handle→send descriptors); live HTTP server + CS-API call box-gated |
| **AS registration** (`as_token`/`hs_token`, namespaces, `url`; one AS per tenant, CA-5) | ✅ **BUILT** — `ASRegistration` dataclass + puppet-namespace enforcement |
| **mxid → `tenant:requester` mapping** + minting the gateway's `token`/`hmac` (CA-4) | ✅ **BUILT** — `nc_channels/matrix_adapter.py` (`identity_from_mxid`, `mint_adapter_hmac`), binds clean to `gateway.normalize/resolve_identity` |
| **outbound streaming render** (tokens → Matrix; incremental vs send-on-complete) | ✅ **BUILT** — send-on-complete (`stream_to_text`/`outbound_message`); `outbound_edit` (`m.replace`) ready for incremental (RISK-1) |
| **infra activation**: deploy Synapse + public CS ingress (reuse `matrix.neuraledge.in`) + the AS container | `[U]`/🔨 — **box-gated** (`service.serve`/`_cs_api_call` raise until a reachable Synapse) |

**Built 2026-06-29 (offline, tested):** `nc_channels/{matrix_adapter,service}.py` + 38 unit tests, all green;
the AS contract confirmed against spec.matrix.org + Synapse docs (registration YAML, `Bearer hs_token`
inbound, `?user_id=` puppeting within the users namespace, `m.replace` edit shape, txnId at-least-once
dedup). The pure core binds verified-clean to the first-party `orchestrator.handle(raw)` seam. What
remains is **box-gated**: the live AS HTTP server (`service.serve`) + the CS-API send (`_cs_api_call`),
which need a reachable Synapse — i.e. subtasks 6–8 below (infra flip + first-contact via Element).

## Subtasks (ordered)
1. **[½d, do FIRST] Confirm the Matrix AS contract against Synapse** — the exact registration YAML, the
   txn-push shape, and the CS send/puppet rules. *This is the spec-vs-source gap below; verify before building.*
2. AS adapter skeleton: an HTTP service exposing the AS txn endpoint + `_matrix/app/v1/{users,rooms}` queries.
3. Inbound mapping `m.room.message → raw` + call `handle` (reuse it verbatim; pass `mode="integration"`).
4. Identity: mxid→`tenant:requester`; mint the per-adapter `token`/`hmac` the gateway expects (CA-4).
5. Outbound: `stream` → Matrix send (start with **send-on-complete**, add incremental edits later — RISK-1).
6. AS registration + provisioning (per-tenant AS, CA-5); a bootstrap room + the seat's Matrix user.
7. Infra: flip Synapse on (targeted apply) + public CS ingress (ALB host rule + ACM TLS on `matrix.neuraledge.in`) + the AS task def.
8. First-contact test: a **stock Element client** logs in → DMs the NEop → gets a streamed reply.

## Named unknowns / risks (honest — the part that hides steps)
- **RISK-1 (highest): Matrix has no native token streaming.** Options: send-on-complete (simplest, slight
  latency), or incremental `m.replace` edits (feels live, risks edit-spam / client rate caps). Spec flow says
  "Matrix CS long-poll V1 → Sliding Sync V2." **Decide in subtask 1; start send-on-complete.**
- **RISK-2: AS registration + puppeting details** (namespaces, `?user_id=` impersonation, `hs_token` verify)
  are **from the Matrix AS spec, NOT yet run against this Synapse** — confirm in subtask 1 (verify-the-child).
- **RISK-3: public ingress is real infra** — TLS cert on the domain + ALB host rule + (federation 8448 only
  if cross-server). `[U]` + a `terraform apply`.
- **RISK-4: `mode="integration"` path** — `handle` is proven in `mode="unit"`; the live-dispatch path runs
  through the **jcode adapter** (gated on T0). So a *fully* live chat→NEop loop depends on M1b; before T0 you
  can demo chat→route→(mocked dispatch). Don't promise live NEop work in chat before T0 passes.

## Effort + confidence
**~1–2 weeks**, confidence **medium** — the seam is first-party-verified (high confidence the adapter binds
cleanly), but RISK-1 (streaming) and RISK-2 (AS-vs-Synapse specifics) carry the band. Subtask 1 (½ day)
collapses most of the uncertainty. **Recommend doing subtask 1 now, in parallel with the jcode T0 box wait.**

## Spec refs
S2 §2.1 (gateway GW-1..6), §2.2 (channel adapters CA-1..5, the NeuralChatMessage envelope), §2.3
(orchestrator COC-1..5); S3 Flow 2 (chat round-trip, streaming). Code: `frontdoor/{gateway,orchestrator,classifier}.py`, `infra/terraform/synapse.tf`.
