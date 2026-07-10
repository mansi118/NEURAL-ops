# nc-web — the branded product client: completion + end-to-end launch plan

Dated 2026-07-10. Track 4 of `technical-plan-3-month-2026-07.md`. nc-web is the largest net-new block and
the surface that turns the alpha into a product. This plans it to completion and to a live launch, and —
critically — it needs none of the gated backend deploys to reach its MVP (branded chat replacing Element),
with the differentiating panels lighting up progressively as their data sources come online.

## The architecture decision that makes this fast: everything rides Matrix

nc-web is a React SPA over `matrix-js-sdk`, talking to the Synapse homeserver we already run
(`matrix.neuraledge.in`, public). There is NO new backend. This is the same insight as the bridge: nc-web
and Element are both just Matrix clients on the same rooms. So:

- Chat — rooms, DMs, threads, timeline, presence, typing, read receipts, E2EE — all come from matrix-js-sdk.
- NEops (Aria, Recon) are `@neop_*` Matrix users; nc-web renders them as first-class assistants (avatar,
  "assistant" styling, per-seat typing) rather than generic users.
- Decision Queue — a dedicated Matrix room. The governance/flywheel/vault harness emit sinks post proposals
  as messages with a custom event type (`m.neop.proposal`); nc-web renders that room as a queue and sends the
  verdict back as a reaction / custom event (`m.neop.verdict`) that the harness consumes. No new API.
- Fidelity dashboard — the fidelity harness publishes per-seat snapshots as Matrix room **state** events
  (`m.neop.fidelity`: maturity, agreement_rate_30d, blended vs human split); nc-web reads room state. No new API.

Consequence: nc-web stays a pure client. Its MVP (branded chat) is launchable the moment it's hosted and
pointed at the live Synapse — independent of the comms tier, schedulers, and live seams. The Decision Queue
and dashboard are progressive enhancement: they render empty until their producer harnesses go live, then
fill in. This is why the UI "must not gate first contact" (neos-ui-matrix-plan.md) and doesn't.

## Stack

- Vite + React + TypeScript. `matrix-js-sdk` for the client. Vitest + Testing Library for units; `tsc
  --noEmit` + `vite build` as the integration gate in CI. Playwright E2E is later (needs a running HS → box).
- Discipline mirror of the Python side: keep LOGIC (event parsing, verdict encoding, timeline reducers,
  fidelity-state decoding) in pure, dependency-light modules that are unit-tested; keep React components thin
  over them. So the "offline-testable, tests-green-before-merge" cycle holds for a frontend too.
- No secrets in the client. Auth is Matrix login (password now; SSO/OIDC later). Homeserver URL is build/env config.

## Phased delivery (each phase = one branch → tested PR → merge, same cycle as the runtime work)

- PR-A — Scaffold. Vite+React+TS app under `nc-web/`, `matrix-js-sdk` dep, config (homeserver base URL), a
  typed `MatrixService` wrapper (login, start/stop sync, list rooms, send), a login screen, and Vitest units
  for the wrapper over a mocked sdk. New CI workflow `.github/workflows/nc-web.yml` (npm ci → tsc → vitest →
  build). Gate: builds, typechecks, tests green. `node_modules/` + `dist/` gitignored.
- PR-B — Core chat. Room list, timeline view, composer, send/receive with optimistic echo, NEop-aware message
  rendering (puppet users as assistants). Pure timeline-reducer + message-model units.
- PR-C — Branding + theme. NeuralChat identity, light/dark (theme-aware), responsive layout, loading/empty/
  error states.
- PR-D — Decision Queue panel. Parse `m.neop.proposal` events → proposal cards; approve/reject → send
  `m.neop.verdict`; optimistic update. Pure parse/encode units. (Data producer = the governance/flywheel/
  vault emit sinks — wired when those deploy.)
- PR-E — Fidelity dashboard panel. Read `m.neop.fidelity` room state → per-seat cards (maturity,
  agreement_rate_30d, blended vs human split from the shadow breakdown). Pure state-decoder units.
- PR-F — Build + deploy pipeline. Production build, nginx conf, deploy script; host at `chat.neuraledge.in`
  (DNS + TLS), pointed at `matrix.neuraledge.in`. This is the box/prod step (gated). END-TO-END LAUNCH.
- Later — nc-admin (tenant/audit read views), SSO/OIDC, streaming replies, non-Matrix channel adapters.

## End-to-end launch sequence

Offline (agent-drivable now, each through the cycle): PR-A … PR-E — a complete, tested, branded client that
builds green, with chat fully functional and the two panels rendering (empty until producers exist).

Live (the launch; box/prod, your go):
1. Build nc-web (`vite build`) → static `dist/`.
2. Host it: nginx vhost `chat.neuraledge.in` on the matrix box (mirrors the existing `element.neuraledge.in`
   pattern) + DNS A record + TLS cert. Point `MATRIX_BASE_URL` at `https://matrix.neuraledge.in`.
3. First contact: open `chat.neuraledge.in`, log into a seat account, chat with Aria/Recon. This is the MVP
   launch — branded product chat replacing Element, needing none of the gated backend work.
4. Progressive enhancement (as each producer deploys): fidelity harness publishes `m.neop.fidelity` → the
   dashboard fills; the governance/flywheel/vault emit sinks post to the Decision Queue room → the queue fills.

So the product launches in two honest stages: branded chat is live as soon as it's hosted (days, gated only
on DNS/TLS/nginx), and the intelligence panels turn on as the merged harnesses get their live seams. Nothing
in PR-A…PR-E waits on a tenant or on the comms-tier apply.

## Testing strategy

- Unit (Vitest): the pure logic modules — `MatrixService` over a mocked sdk, event parsers, verdict encoders,
  timeline reducers, fidelity-state decoders. This is the bulk and it is what the per-PR gate enforces.
- Type + build: `tsc --noEmit` and `vite build` in CI catch integration breakage.
- E2E (Playwright, later): against a running HS in a box session — the frontend analogue of the box-gated
  live Matrix test; it does not gate merges.

## What stays gated (yours)

Only the launch step (PR-F): DNS `chat.neuraledge.in`, the TLS cert, and the nginx vhost on the matrix box.
Everything else — the entire client and its tests — is offline and agent-drivable through the normal cycle.
