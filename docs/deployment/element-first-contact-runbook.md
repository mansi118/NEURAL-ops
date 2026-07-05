# Element first-contact runbook (2026-07-01)

> **Scope.** The exact, ordered, gate-tagged steps to reach **first contact through a frontend** — log
> into a seat in **Element** (the zero-build, stock Matrix client) and round-trip a message through the
> spine. Element writes **no code**; "connect a frontend" is therefore entirely **deploy + box**, and this
> runbook's job is to make that execution mechanical by naming every unknown *now*, offline.
>
> This is the client-side twin of `nc-channels-as-contract.md`: that doc shrank the AS↔Synapse unknown to
> *transport*; this one shrinks the frontend↔homeserver unknown to *deploy reachability*. Companion to
> `neos-matrix-integration-plan.md` (the wiring) and `neos-ui-matrix-plan.md` (the strategy).

## Readiness — what's true, traced against the live infra (read first)
The offline contracts are confirmed (AS-side 46/46, orchestrator seam green, backbone 0-warning). But the
**deploy** is not Element-reachable yet. Tracing `infra/terraform/synapse.tf` + `variables.tf` surfaced
three gaps that block first-contact and must be closed at deploy time — none are offline-fixable beyond
authoring the TF:

| # | Gap (traced) | Why it blocks Element | Fix (deploy-gated) |
|---|---|---|---|
| **G-A** ✅ authored | `synapse_server_name` default = **`neuraledge.local`** (`variables.tf:250`), not publicly resolvable | A `.local` `server_name` is not resolvable; mxids (`@seat:neuraledge.local`) won't federate or resolve | **DONE (config):** `synapse_server_name = "matrix.neuraledge.in"` set in `phase2.tfvars` + `phase3.tfvars`, overriding the `.local` default. Chose the **self-contained** name (server_name == the homeserver's own address) over the `neuraledge.in` **delegation** form specifically to avoid a *permanent* apex `.well-known/matrix/*` dependency (server_name is immutable at first boot, so a discovery path you can't serve is unrecoverable). Must be set *before* the first comms-tier apply. Apply still deploy-gated; G-B is then plain public ingress at `https://matrix.neuraledge.in` — **no delegation, no `.well-known`.** |
| **G-B** | Synapse is **internal-only** — SG ingress from `var.vpc_cidr` on `:8008`, Cloud Map `synapse.<ns>:8008`, **no public ALB** (`synapse.tf:69-88`) | Element on a laptop is outside the VPC and cannot reach an internal Cloud Map address | add a public **HTTPS ALB → :8008** for the Synapse client API + TLS cert, **or** run Element inside the VPC (bastion / SSM port-forward) for the very first smoke |
| **G-C** | **AS registration not mounted** — the Synapse task env sets `SYNAPSE_SERVER_NAME`/`REPORT_STATS` only; no `app_service_config_files`; and **no nc-channels ECS service exists** in the TF | Synapse won't route the seat's rooms to the bridge, so messages never reach `orchestrator.handle` | mount `registration_yaml(...)` (from `nc_channels/registration.py`) into Synapse's `homeserver.yaml` `app_service_config_files`; add an nc-channels Fargate service + internal route so the HS can `PUT` transactions to it |

**⇒ "Connect Element" is not one gate, it's three deploy deltas (G-A/B/C) on top of the two you already
hold (M1b box-session + comms-tier flip).** All three are bounded TF/config changes; authoring them is
offline, applying them is the deploy gate.

## Prerequisites (gates, in order)
1. `[BOX]` **M1b proven** — `gap1`+`gap2` green, the four PRs merged. The runtime must actually serve a seat
   before a frontend has anything to talk to.
2. `[DEPLOY]` **comms-tier up** — `enable_comms_tier = true` (`phase2.tfvars`): Synapse + RDS + EFS + Redis +
   NATS. (Synapse resources are all `count = enable_comms_tier ? 1 : 0`.)
3. `[DEPLOY]` **G-A/B/C closed** — public server_name, public client-API ingress, AS registration mounted +
   nc-channels service running. Without these Element cannot reach or round-trip.

## In-session reachability (the G-B deferral path — pin this BEFORE the box)

G-B (public HTTPS ALB → `:8008`) is correctly deferred — first contact does **not** need a public
homeserver. But "defer the ALB" must not silently become "defer *reachability*": Element still has to reach
the internal Synapse (`synapse.<name>.local:8008`, private subnets) somehow in the session. Pin the path now
so it isn't the thing you discover is missing at first contact. Traced: **there is no bastion / SSM host /
tailnet in `infra/terraform` today** — so the reachability substrate is itself a small pre-flight, not a
given.

**Recommended alpha path — SSM port-forward, no new public ingress, no TLS:**
1. A minimal SSM-managed jump instance in a private subnet (or reuse any SSM-registered box in the VPC).
2. `aws ssm start-session --target <id> --document-name AWS-StartPortForwardingSessionToRemoteHost
   --parameters '{"host":["synapse.<name>.local"],"portNumber":["8008"],"localPortNumber":["8008"]}'`
   → laptop `localhost:8008` tunnels to the internal homeserver.
3. **Element _Desktop_** (not Web) → homeserver `http://localhost:8008`. Element Web (a browser secure
   context) refuses a plaintext `http://` homeserver; Element Desktop accepts `localhost` over http, so the
   alpha smoke needs **no TLS and no cert** — the self-contained `server_name` (G-A) means there's no
   `.well-known` to serve either. mxids show as `@seat:matrix.neuraledge.in` regardless of the tunnel URL.

**Alternatives** (pick one, don't improvise live): a Tailscale subnet-router task advertising the VPC CIDR
(laptop on the tailnet reaches `10.40.x` directly); or bring G-B forward (public ALB + ACM cert + Element
Web) if you want the real ingress in this window anyway. The SSM path is the smallest and is the default.

## First-contact steps (each gate-tagged; mechanical once prereqs hold)
1. `[DEPLOY]` **Generate the AS registration** — `python -c "from nc_channels.registration import registration_yaml; ..."`
   with the tenant's `ASRegistration` (real `as_token`/`hs_token` from Secrets Manager, **never committed**).
   `validate_registration_dict` runs inside `registration_yaml` — fail-closed.
2. `[DEPLOY]` **Mount it** — write the YAML to Synapse's config volume (EFS) and add its path to
   `app_service_config_files` in `homeserver.yaml`; restart the Synapse task. (Closes G-C, HS side.)
3. `[DEPLOY]` **Stand up nc-channels** — Fargate service running `ASService.serve` (the box-gated HTTP
   transport), reachable from Synapse at the `url` baked into the registration. (Closes G-C, AS side.)
4. `[DEPLOY]` **Create the bot + a seat** — register the `@neos-bot` sender_localpart user; create the seat's
   human user (`@seat-name:<server_name>`); create one room and invite both the human and `@neos-bot`. The
   `@neop_*` puppet namespace is reserved exclusively by the registration (no manual creation).
5. `[LIVE]` **Element config** — open Element (web or desktop, stock), **Sign in → Edit → Homeserver** =
   `https://matrix.<domain>` (the public client API from G-B); log in as the seat's human user; open the
   seat room.
6. `[LIVE]` **Round-trip** — send a message in the room. Expected path:
   `Element → Synapse → PUT /_matrix/app/v1/transactions → nc-channels → matrix_message_to_raw →
   frontdoor.orchestrator.handle → runtime (seat-serve) → /mcp palace → reply_send (@neop_* puppet) →
   Synapse → Element`. A puppet reply appears in the room. **That is first contact.**

## Acceptance criteria
- The seat's human message produces an `@neop_*` reply **in the same room**, end-to-end, no manual nudging.
- The reply reflects memory/runtime behaviour (not a canned echo) — i.e. the `/mcp` retrieval actually ran.
- No `_admin` bypass: the seat's neopId is scoped (the shim bakes it); an unseeded seat is DENIED, not served.

## Failure triage (the unknowns this runbook deliberately narrows to)
Because the *contract* is confirmed offline, a first-contact failure is almost certainly **transport/deploy**,
not logic. Check in this order:
1. **Element can't reach the homeserver** → G-B (no public ingress / TLS). Point Element's homeserver
   directly at `https://matrix.neuraledge.in` — with the self-contained `server_name` (G-A) there is **no
   `.well-known` delegation** to get wrong; the base URL *is* the server_name.
2. **Login works, messages vanish** → G-C (registration not loaded, or nc-channels URL unreachable from the HS).
3. **`@neop_*` reply rejected by the HS** → namespace mismatch between the registration regex and the puppet mxid.
4. **Seat served as `_admin` / denied** → scope not baked (shim env `PALACE_ID`/`NEOP_ID`); see CLAUDE.md SHARP EDGE.

## Bottom line
Element is the right first-contact frontend (zero build), and the only reason "connect it" isn't a single
command is **deploy reachability**, which this runbook now enumerates as G-A/B/C. None cross a new gate
beyond the two that are yours (box-session + comms-tier deploy); all three are bounded TF/config deltas,
authorable offline, appliable only on the box. nc-web (the product UI) stays deliberately deferred to
post-M1b per the integration plan — Element covers first contact.
