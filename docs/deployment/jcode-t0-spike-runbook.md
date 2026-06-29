# jcode T0 Spike — Go/No-Go Run-Book

**Goal:** run ONE jailed jcode seat end-to-end against the live palace and confirm the
adapter's contract holds — the T0 go/no-go gate from `docs/neop-jcode-adapter-implementation-plan.md`
§4. **Done (plan DoD):** `jcode run "remember <fact>; then search <fact>"` round-trips through the shim
to the palace and a row lands in Convex under the test scope, **and** the model-key path is green.

**This is `[U]` / box-gated — it is NOT run from the WSL dev box.** It needs a target host with Docker
(EC2 ap-south-1 Graviton, or a Mac-mini under Colima). Nothing below has been executed; this is the
exact replay recipe. T0 is **STOP-and-show**: run it, show the result, do not proceed to T9 (first real
NEop) without sign-off. v1 is **NeuralEDGE-tenant only** — no client data on a seat until T7 red-team passes.

**Honest framing:** a green T0 proves the wiring (jail + shim scope-lock + round-trip + safety gate). It
is NOT "production-ready" (that's the Day-90 gate) and NOT the T7 isolation proof (a separate hard gate).

---

## The four prerequisites (T0's gates)
| # | Prereq | How to satisfy on the box | Status |
|---|--------|---------------------------|--------|
| 1 | A runnable **jcode** binary | build/install `1jehuang/jcode`@master on the host (or in the seat image). `jcode --version` works. | box |
| 2 | A **model key** | `ANTHROPIC_API_KEY` (direct) **or** `OPENROUTER_API_KEY` (the on-hand path; chosen by key-availability, NOT a Bedrock block — Bedrock generative works in-VPC, only Anthropic-on-Bedrock is gated). Rides the env, never config/argv. | key |
| 3 | A **live palace** `/mcp` | already LIVE — Convex on AWS (`docs/deployment/dogfood-spine-runbook.md`); the `.convex.site` URL + a test `(palaceId, neopId)` + the signing keyref. | ✅ |
| 4 | **Docker** | present on the target host (not WSL). | box |

The adapter package (`neop_jcode_adapter`) is `pip install -e .`-able on the host; it is pure-stdlib
except the optional `cryptography` (Ed25519 signing — forward-looking, see CLAUDE.md invariant #1).

---

## Phase A — Render the seat (no Docker, no network) `[A]`
Pick the test scope + a Class for the spike. Use **Class A with the jail enforced** for the round-trip
(palace auto-allow), or **Class B** to also exercise the safety gate (Phase D).

```bash
export PALACE_MCP_URL="https://<deployment>.convex.site/mcp"   # the .site HTTP-actions endpoint
export PALACE_ID="<test_palaceId>"        # e.g. k17f0b36y2f7h4sbr3pqp5wxg189cvg1 (neuraledge)
export NEOP_ID="t0_spike"                  # the seat's neopId (NEVER blank → blank = _admin ACL bypass)
export SEAT_HOME="$PWD/.jcode-seats/$PALACE_ID__$NEOP_ID"

python3 - <<'PY'
import os
from neop_jcode_adapter.config_render import ConfigRenderer, ANTHROPIC_PROVIDER
r = ConfigRenderer()
seat_class = "A"; jail = True            # A+jail = palace auto-allow + live bash inside the jail
home = os.environ["SEAT_HOME"]
rs = r.render(
    palace_id=os.environ["PALACE_ID"], neop_id=os.environ["NEOP_ID"],
    seat_class=seat_class, jcode_home=home,
    palace_mcp_url=os.environ["PALACE_MCP_URL"],
    signing_key_ref="env:PALACE_SIGNING_KEY_T0",     # a keyref; the key value rides the container env
    provider=ANTHROPIC_PROVIDER,                      # or OPENROUTER_PROVIDER for the OpenRouter path
    pre_tool_hook=r.pre_tool_command(),              # wires [hooks].pre_tool → the T5 gate
    jail_enforced=jail, swarm_enabled=False,
)
print("wrote", rs.config_toml_path, "+", rs.mcp_json_path)
print("disabled_tools:", rs.disabled_tools)
# the baked per-seat policy the pre_tool hook reads (inject into the container env, Phase C):
print("hook_env:", r.hook_env(seat_class, swarm_enabled=False, jail_enforced=jail))
PY
```
**Verify:** `config.toml` has `default_provider`, `[tools].disabled`, and `[hooks].pre_tool`; `mcp.json`
has `servers.cortex-palace` with `shared: false` and the baked `PALACE_ID`/`NEOP_ID`. **No secret on disk**
(grep the home for `sk-ant`/`sk-or-`/`BEGIN PRIVATE KEY` → must be empty).

## Phase B — Resolve the fail-closed jail (no Docker call yet) `[A]`
```bash
python3 - <<'PY'
import os
from neop_jcode_adapter.isolation import build_jail_spec
seat = (os.environ["PALACE_ID"], os.environ["NEOP_ID"])
spec = build_jail_spec(
    seat, image="neos-jcode-seat:latest",
    palace_mcp_url=os.environ["PALACE_MCP_URL"],
    workdir_mount=os.environ["SEAT_HOME"],
    env_passthrough=["ANTHROPIC_API_KEY", "PALACE_SIGNING_KEY_T0"],  # NAMES only — values from env
)
print("network:", spec.network_name)
print("egress_allowlist:", spec.egress_allowlist)   # ONLY the palace host + the model host
print("docker_args:", " ".join(spec.docker_args))
PY
```
**Verify:** `egress_allowlist` is exactly `{palace host, model host}`; `docker_args` includes
`--read-only --cap-drop ALL --security-opt no-new-privileges` + the per-seat `--network` + the single
`-v <home>:/work` bind. (`build_jail_spec` refuses blank scope / a secret value in `env_passthrough`.)

## Phase C — Launch the jailed seat `[U]` (Docker; the box step)
The per-seat network must be egress-firewalled to `egress_allowlist` (drop all other outbound). Create
it, then run jcode inside the jail with the seat env (model key by name, never on the argv):
```bash
docker network create "$(python3 -c 'from neop_jcode_adapter.isolation import build_jail_spec,*' ...)"  # spec.network_name
# Apply the egress firewall to that network so ONLY spec.egress_allowlist hosts resolve/connect.
# (firewall mechanism is host-specific — iptables/nftables on the per-seat bridge, or a sidecar proxy.)

# seat env: distinct JCODE_HOME + the baked hook policy + the model key (by value from the launcher env)
docker run <spec.docker_args> \
  -e ANTHROPIC_API_KEY -e PALACE_SIGNING_KEY_T0 \
  -e NEOP_SEAT_CLASS=A -e NEOP_SWARM_ENABLED=0 -e NEOP_JAIL_ENFORCED=1 \
  -e JCODE_HOME=/work \
  neos-jcode-seat:latest \
  jcode run "remember that the T0 canary fact is squamous-pangolin-1917; then search squamous-pangolin" --json
```
jcode reads `/work/config.toml` + `/work/mcp.json`, spawns the shim (`python -m
neop_jcode_adapter.palace_mcp_shim`, scope baked from `PALACE_ID`/`NEOP_ID`), and routes palace_remember
/ palace_search through it. (`supervisor.build_run_argv` / `seat_env` produce this argv+env in code.)

## Phase D — The verifies (the definition of done) `[U]` to run, `[A]` to check
1. **Round-trip (the gate):** the `search squamous-pangolin` result contains the canary fact →
   remember+search round-tripped through the shim to the palace. **AND** confirm the Convex row exists
   under `(PALACE_ID, NEOP_ID)` (palace query / `tools/deployed_stack_smoke.py`-style check).
2. **Model-key path green:** the run completed (the model answered) → prereq #2 works (either provider).
3. **Audit coverage:** `$SEAT_HOME` (or `NEOP_AUDIT_DIR`) has a jsonl row per palace op (allow rows for
   the remember+search). This is the leak-detector while ACL is honest-caller.
4. **Scope-lock (negative):** a request carrying `palaceId`/`neopId` in the tool args is rejected by the
   shim (a `scope_spoof` deny row, attempted KEYS only) — the model can never widen its own scope.
5. **Safety gate (run a Class-B seat):** render+launch a Class B seat, then `jcode run "use bash to cat
   /etc/hostname"` → the pre_tool hook exits 2 → **blocked** (and a TOOL_LIFECYCLE blocked event). Swarm
   is allowed for B (grant) and denied for C — the dynamic tier.
6. **Promotion (T6):** inside the seat, `jcode memory export /work/mem.json --scope all`, then on the host:
   ```bash
   python3 - <<'PY'
   from neop_jcode_adapter.memory_promoter import MemoryPromoter, make_shim_writer
   from neop_jcode_adapter.palace_mcp_shim import shim_from_env   # env already has PALACE_* set
   res = MemoryPromoter().promote(MemoryPromoter.load_export("$SEAT_HOME/mem.json"),
                                  make_shim_writer(shim_from_env()))
   print(res)   # promoted durable items; inactive/empty skipped
   PY
   ```
   **Verify:** the durable canary fact appears in the palace; ephemeral chatter does not.

## Phase E — Honest status `[A]`
Record the result (go or no-go) + the exact image/commit/scope used. On GO: T0 is the green light for
T1–T6 *integration* validation on the box (the unit cores are already green), then the **T7 red-team
isolation suite** (the hard gate before any client data). On NO-GO: capture which phase failed + the
shim/jcode logs; do not proceed.

---

## Go / No-Go criteria (objective)
- **GO** ⇔ Phase D #1 (round-trip + Convex row) **and** #2 (model-key path) are both green.
- Strong-GO (recommended before T1 integration): #3 audit, #4 scope-lock, #5 safety gate also green.
- **NO-GO** ⇔ the round-trip fails, OR scope-lock #4 fails (a scope-spoof reaching the palace is a
  **hard stop** — the chokepoint is the whole point), OR the jail can't be brought up fail-closed.

## What this run-book deliberately does NOT do
- It does not run T7 (red-team: cross-tenant read, scope spoof at scale, egress/fs escape, key exfil) —
  that is the milestone-critical gate, run separately and only after a strong-GO here.
- It does not authorize a Class A self-dev loop or any client data on a seat (T9 / T7 gates).
- The egress-firewall mechanism (Phase C) is host-specific and is the one piece the adapter does not
  emit — `build_jail_spec` produces the allowlist; binding it to the network is an ops step on the box.
