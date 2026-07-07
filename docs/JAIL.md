# JAIL.md — the NEop egress jail (GAP-2 single source of truth)

> **Confidentiality:** INTERNAL — NeuralEDGE / Synlex.
> **What this is.** The spec the code `neop_jcode_adapter/isolation.py::build_jail_spec` **implements**, and
> the SoT the runtime image (`pi-neop-runtime/Dockerfile`) points at instead of re-expressing egress rules.
> If this doc and the code disagree, **the code is authoritative and this doc is the bug** — they are kept in
> lockstep on purpose (a dangling/where-drift SoT pointer is exactly the asserted-equivalence failure GAP-2
> exists to close). Every rule below is asserted by `tests/test_isolation.py` + `tests/test_redteam_isolation.py`.

## Why a jail at all (the load-bearing reason)
The 4-layer ACL is **fail-OPEN until S0.3** (CLAUDE.md invariant): a missing/blank scope defaults server-side
to `_admin`, which **bypasses all ACL**. While that is true, **the container boundary CARRIES tenant
isolation** — one jail per `(palaceId, neopId)`, maximally locked and fail-closed. The jail is **runtime-agnostic**:
the jcode image and the Hermes/Pi Node image (`pi-neop-runtime`) are fed to the *same* `build_jail_spec` as
different `image=` values — never a second, hand-written egress spec (that divergence is the drift GAP-2 kills).

## Offline vs box (what this repo can prove, and what it cannot)
- **OFFLINE (proven here):** the jail **policy** — `egress_allowlist()` + `build_jail_spec()`: the exact
  `docker run` lockdown flags and the egress allowlist the network layer must enforce, with fail-closed
  validation. 77 tests green.
- **BOX-GATED (T0/red-team):** `_docker_run` — the actual container start, the egress firewall/proxy that
  *enforces* the allowlist, and the adversarial **cross-tenant** isolation proof. **Policy-correct ≠
  enforced.** The offline half makes the box pass mechanical; it does not substitute for it.

## The lockdown (`build_jail_spec` → `docker_args`)
Every seat container runs with, and only with:

| Flag | Why |
|------|-----|
| `--network neop-<pid>-<nid>` | **Per-seat** network, NOT the shared default bridge — the egress firewall binds to it and drops everything not in the allowlist. |
| `--read-only` | Immutable rootfs — no persistence, no tampering with the runtime. |
| `--cap-drop ALL` | No Linux capabilities. |
| `--security-opt no-new-privileges` | No setuid escalation. |
| `--pids-limit 256` · `--memory 2g` · `--cpus 1.0` | Resource bounds (fork-bomb / exhaustion containment). |
| `--tmpfs /tmp:rw,noexec,nosuid,size=256m` | The only writable scratch; `noexec`/`nosuid`. |
| `--workdir /work` + **exactly one** `-v <seat-workdir>:/work` | The **single** host bind — a per-seat working dir. Rootfs is read-only, so this is the highest-leverage escape vector; nothing else is mounted. |
| `-e NAME` (names only) | Secrets are forwarded **by name**; the value lives in the launcher env, **never on the docker arg line / disk**. A `NAME=value` in `env_passthrough` is refused. |

**Image requirement (why the runtime image matters too):** the image must run **non-root** and write **only**
`/work` + `/tmp`, or `--read-only` breaks. `pi-neop-runtime/Dockerfile` ships `USER node` (uid 1000) — this
closes the **live-T7 uid-0-in-container gap** — and writes nothing outside those two paths.

## Fail-closed refusals (a jail that can't be locked must NOT launch)
`build_jail_spec` / `egress_allowlist` **raise** (never launch) on:
- blank `palaceId`/`neopId` (the `_admin`-bypass path),
- blank `image` or blank `workdir_mount`,
- a `workdir_mount` that is the docker socket, any sensitive host path (`/`, `/etc`, `/proc`, `/sys`, `/dev`,
  `/root`, `/var/run`, `/var/lib`, …), non-absolute, or un-normalized (`..`, `//`, `./`),
- a secret **value** in `env_passthrough` (`NAME=value`),
- a **blank/unparseable** palace URL, or an **unknown provider** (exact-match only).

## Egress allowlist — the ONLY hosts out (default-DROP)
The jail permits egress to **exactly two** hosts and drops everything else:
1. the **palace MCP host** (parsed from `PALACE_MCP_URL`), and
2. the **model-provider host**, from `config_render.PROVIDER_EGRESS_HOST[provider]`.

Any third host is a finding. The provider→host map (`config_render.py`):

| provider (`= runtime provider id`) | egress host |
|------------------------------------|-------------|
| `anthropic-api` | `api.anthropic.com` |
| `openrouter` | `openrouter.ai` |
| **`amazon-bedrock`** (Decision 2) | **`bedrock-runtime.ap-south-1.amazonaws.com`** |

### The Bedrock-in-VPC entry (Decision 2 — read this before touching the allowlist)
Deploy-topology **Decision 2** made the Hermes sealed-spine model path **Bedrock/Nova in-VPC**. The jail must
permit it, **or the jail silently blocks the very model path the spine depends on** — and that failure surfaces
**at the box, in-VPC, at generate time**, presenting as *"Nova won't answer"* when the real cause is the egress
policy dropping the connection. That is the landmine GAP-2's trace caught: two independently-correct
workstreams (the Bedrock provider `pi-neop-runtime#8` and the T7 jail) collide at their intersection.

Two properties to hold:
- **Provider id matches the runtime, not jcode config.** `amazon-bedrock` is pi-ai's `KnownProvider` /
  `pi-neop-runtime`'s `ModelBroker` id — it is an **egress-map** entry only. The jcode-config `render()` still
  whitelists `anthropic-api | openrouter`; Hermes is configured by env, so this is not a contradiction.
- **host-in-map ≠ connection-succeeds.** The host is the **region-pinned** endpoint
  `bedrock-runtime.ap-south-1.amazonaws.com` (us-east-1 403s — the bearer token is region-scoped). In-VPC it
  resolves via the **PrivateLink interface endpoint** (`infra/terraform/endpoints.tf`: `bedrock-runtime` in the
  interface set, `private_dns_enabled = true`), so the allowlist entry is the **standard regional hostname**,
  not a `vpce-*` name. The **box firewall must permit that resolution path** — a hostname/SNI-filtering proxy
  works with this host; an IP-filtering firewall must allow the endpoint ENI IPs. **The box proof confirms the
  call actually succeeds; this doc + the tests only prove the host is correctly in the policy.**

### Provider vocabulary for the launcher
`egress_allowlist(..., provider=...)` defaults to `anthropic` (unchanged, to not alter existing jcode-path
callers). **The Hermes sealed-spine launcher MUST pass `provider="amazon-bedrock"` explicitly** — otherwise the
default allows `api.anthropic.com` and the in-VPC Bedrock call is dropped.

## Where each guarantee is proven
- **Lockdown + single-bind + env-names-only + fail-closed refusals:** `tests/test_isolation.py`,
  `tests/test_redteam_isolation.py` (offline).
- **Egress = exactly {palace, model host}, incl. the Bedrock path:** `test_egress_bedrock`,
  `test_hermes_bedrock_jail_allows_the_decided_model_path`, `test_egress_allowlist_is_exactly_palace_plus_model_host`.
- **Enforcement (firewall drops a third host) + cross-tenant adversarial isolation:** **BOX** — `_docker_run`
  on the T0 box + `test_redteam_isolation.py` against a live second tenant palace. Downstream of the box + a
  second palace; this is a **real gate before a second real tenant**, never skipped.
