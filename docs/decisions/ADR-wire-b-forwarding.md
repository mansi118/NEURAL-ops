# ADR-wire-b-forwarding — How nc-channels reaches the live NEop runtime (Wire B)

> **Status:** DECIDED 2026-07-07 · **Owner:** ML
> **Date:** 2026-07-07 · **Confidentiality:** CONFIDENTIAL — INTERNAL (NeuralEDGE)
> **Depends on:** `ADR-neop-runtime` (runtime = Hermes/`pi-neop-runtime`, DECIDED 2026-06-30)
> **Context:** `docs/deployment/wiring-map.md` (Wire B), `docs/deployment/bar1-open-questions.md` (#86)

---

## Why this ADR exists
`ADR-neop-runtime` decided the NEop inner loop runs on **Hermes (Node/TS, `pi-neop-runtime`)**. But the
Matrix bridge `nc_channels/service.py` today calls `frontdoor.orchestrator.handle` **in-process, in Python**.
Python and Node **do not compose in-process**. So the moment Bar 1a's hardcoded reflect gives way to a real
NEop reply (Bar 1b), there is a fork that was never adjudicated: *how does the Python AS bridge reach the
Node runtime?* Left unwritten, a future session picks one by accident. This ADR picks it on purpose.

## The fork
- **B-fwd — nc-channels stays a thin Python transport, forwards `raw` to Hermes over the network.** Hermes
  serves the seat and owns dispatch + memory. The bridge never runs the runtime. `serve(reflect=False)`
  becomes "POST `raw` to the Hermes seat endpoint, stream the reply back."
- **B-port — the bridge logic is reimplemented inside Hermes** and the Python `nc_channels` is retired after
  Bar 1a proves the transport.

## Decision — **B-fwd**
Three reasons, the third decisive:
1. **Keeps the proven transport.** Wire A (`serve()`/`_cs_api_call`, PR #87, 47/47) is done and box-proven at
   Bar 1a. B-fwd redeploys that exact Python code unchanged; B-port throws it away and re-proves the AS
   handshake in a second language.
2. **Makes the seam explicit and jailable.** The Python↔Node boundary becomes a real network call — which can
   be authenticated, scope-checked, rate-limited, and confined by the GAP-2 egress jail. In-process coupling
   (B-port's alternative, or a naive shell-out) hides that boundary where it can't be governed.
3. **B-port would re-fork a runtime the ADR already said NOT to fork.** `ADR-neop-runtime` + CLAUDE.md:
   *"jcode/Hermes is configured, never forked."* Reimplementing the bridge *inside* Hermes is exactly the
   kind of runtime divergence that decision forbids. B-fwd treats Hermes as a service you call; B-port treats
   it as a codebase you edit. The former honors the standing decision; the latter reopens it.

## Consequence to BANK — the forwarding seam is a TRUST boundary, not just a transport hop
Because B-fwd makes bridge→runtime an explicit HTTP call, that call **inherits the system's fail-closed
posture**. When Bar 1b builds it, it MUST:
- **Authenticate** — the bridge proves identity to Hermes; Hermes rejects unauthenticated callers. NOT a
  naked `localhost` POST that any co-resident process on the box can hit.
- **Carry scope, baked + signed** — the `(palaceId, neopId)` seat scope is set by the bridge and never taken
  from the forwarded payload's model-controlled fields, mirroring the palace shim's scope discipline
  (CLAUDE.md invariant: "NEVER accept scope from the model").
- **Fail closed on blank/mismatched scope or auth** — same as `enforce.ts` and the shim.
This is **not** a Bar 1a concern (reflect has no runtime hop). It is a birth-requirement for the Bar 1b seam:
do not ship a naked localhost forward and retrofit auth later.

## Status of the wire
BLOCKED on **M1b** (`pi-neop-runtime` checkout + GAP-1 `memory.ts` /mcp broker + GAP-2 Node egress jail).
This ADR removes the *architectural* uncertainty so that when M1b lands, the integration shape is already
decided: a thin authenticated `raw`-forward from the Python bridge to the Hermes seat endpoint.
