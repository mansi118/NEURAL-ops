# Bar 1a — box runbook (cold, copy-paste, driven by you on the matrix box)

> Prove **Wire A** (Matrix transport) end-to-end against the real production Synapse: Element → Synapse →
> `nc-channels` → CS-API reply → Element, returning `echo ⟳ <text>`. This is a HANDS-ON-THE-BOX session on
> `ubuntu@13.201.114.109` (`matrix.neuraledge.in`), your hands only — it touches a homeserver that has
> served real traffic since April. Every irreversible/risky step below is guarded and its rollback is inline.
>
> **What a green echo proves:** the transport round-trips (Element↔Synapse↔bridge↔Synapse↔Element).
> **What it does NOT prove:** a NEop, memory, or ranking — those are Wire B (runtime/M1b) and Wire C
> (palace), still blocked (see `wiring-map.md` #88). The success line is **"Bar 1a shipped: transport
> proven"** — not "the system works." Read the echo for exactly what it proves, no more.
>
> **This deployment is deliberately ephemeral.** Bar 1a co-locates the bridge on the matrix box to prove the
> transport cheaply. The *permanent* home is the spine VPC behind the #84 ALB (Bar 2 — a redeploy, not a
> toggle; `wiring-map.md`). So an ansible/playbook re-render that later drops this registration is FINE —
> you don't want this co-located bridge to be permanent. Prove, then tear down (Step 8).

---

## Preconditions (confirm before starting)
- SSH works: `ssh ubuntu@13.201.114.109` (key at `/mnt/c/Users/LENOVO/Downloads/aws-server.pem`, chmod 600).
- You can `sudo` on the box and run `docker`.
- PR #87 merged to `main` (or use branch `wip-bar1a-serve`) — the box needs `nc_channels/` + `tools/run_nc_channels_bar1a.py`.
- Element logged in as your admin (`@mansi-neop:neuraledge.in`) to create a room + invite the bot.

---

## STEP 0 — locate the deployment (READ-ONLY; derive, never assume)
Everything downstream depends on four facts about THIS box. Read them off the running system; do not trust
this doc's guesses. On the box:

```bash
# 0a. the Synapse container name (expected: matrix-synapse)
docker ps --format '{{.Names}}\t{{.Image}}' | grep -i synapse
SYN=matrix-synapse   # <- set to whatever 0a printed

# 0b. where homeserver.yaml lives on the HOST (via the container's mounts)
docker inspect "$SYN" --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
#   Find the mount whose Destination holds the config (homeserver.yaml is usually at <dest>/homeserver.yaml,
#   dest commonly /data). Note BOTH sides: HOST_CFG (Source) and CTR_CFG (Destination).
HOST_CFG=/matrix/synapse/config      # <- Source from 0b (VERIFY — may differ on this box)
CTR_CFG=/data                        # <- Destination from 0b (VERIFY)
sudo test -f "$HOST_CFG/homeserver.yaml" && echo "OK: homeserver.yaml found" || echo "STOP: wrong HOST_CFG"

# 0c. the docker network Synapse is on (the bridge must share it so Synapse can reach the bridge)
docker inspect "$SYN" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}'
NET=matrix           # <- set to whatever 0c printed (matrix-docker-ansible-deploy uses "matrix")

# 0d. is this config ANSIBLE-managed? (changes how permanent your edit is — not whether it works now)
sudo head -3 "$HOST_CFG/homeserver.yaml" | grep -qi "maintained by ansible\|do not edit\|managed by" \
  && echo "ANSIBLE-MANAGED: your direct edit works NOW but a playbook re-run will drop it (fine — ephemeral)" \
  || echo "hand-editable: direct edit persists until you remove it"

# 0e. confirm the homeserver is healthy BEFORE you touch anything (your baseline to compare against)
curl -sf https://matrix.neuraledge.in/_matrix/client/versions >/dev/null && echo "baseline: CS-API up" || echo "STOP: CS-API already down — do not proceed"
```
If 0d says ANSIBLE-MANAGED and you want this to *persist*, the durable path is the ansible var
`matrix_synapse_app_service_config_files` + re-run the playbook — but for a Bar 1a proof the direct edit
below is correct and simplest; just know it's ephemeral (which you want).

---

## STEP 1 — mint the token pair ONCE (used in two places; a mismatch is the "403 for no reason" failure)
The `hs_token` (Synapse→bridge auth) and `as_token` (bridge→Synapse auth) must be IDENTICAL in the
registration Synapse reads and in the bridge process. We mint them once into one env file so they *cannot*
drift apart. On the box:

```bash
umask 077
cat > ~/nc-bar1a.env <<EOF
AS_TOKEN=$(openssl rand -hex 32)
HS_TOKEN=$(openssl rand -hex 32)
AS_URL=http://nc-channels-bar1a:8010
AS_USER_REGEX=@neop_.*:neuraledge\.in
AS_SENDER=neos-bot
AS_SERVER_NAME=neuraledge.in
AS_TENANT=neuraledge
HS_BASE_URL=https://matrix.neuraledge.in
LISTEN_HOST=0.0.0.0
LISTEN_PORT=8010
EOF
chmod 600 ~/nc-bar1a.env
echo "minted; tokens live only in ~/nc-bar1a.env (600)"
```
- `AS_USER_REGEX=@neop_.*:neuraledge\.in` — the mxid domain is the **delegated `server_name` `neuraledge.in`**
  (confirmed off this live box, #85), **NOT** the client URL `matrix.neuraledge.in`. Do not "fix" it to match
  the client URL — that rejects every puppet mxid with `M_EXCLUSIVE`. Locked here so it can't drift back.
- `AS_URL=http://nc-channels-bar1a:8010` — the name Synapse (in its container) uses to reach the bridge on
  the shared docker network (Step 6). **Not** `localhost` — container localhost ≠ host localhost.
- `HS_BASE_URL=https://matrix.neuraledge.in` — the bridge's reply hop uses the public TLS CS-API (always
  reachable, TLS, and identical to how Bar 2 will do it). The `as_token` is accepted there.

---

## STEP 2 — get the code on the box
```bash
# clone (private repo — use your GH creds); branch wip-bar1a-serve until #87 is merged, else main
git clone https://github.com/mansi118/NEURAL-ops.git ~/neural-ops || (cd ~/neural-ops && git fetch)
cd ~/neural-ops && git checkout wip-bar1a-serve && git pull
# fallback if the box has no GH access: scp from your dev box
#   scp -r nc_channels tools requirements.txt ubuntu@13.201.114.109:~/neural-ops/
```

---

## STEP 3 — emit the registration YAML (from the SAME env → tokens guaranteed to match)
```bash
cd ~/neural-ops
docker run --rm --env-file ~/nc-bar1a.env -v "$PWD":/app -w /app python:3.12-slim \
  sh -c "pip install -q pyyaml && python3 tools/run_nc_channels_bar1a.py --emit-registration" \
  | sudo tee "$HOST_CFG/nc-channels-registration.yaml" >/dev/null
sudo chmod 640 "$HOST_CFG/nc-channels-registration.yaml"
# eyeball it: id/url/tokens/sender/regex present, tokens ONLY in their own fields
sudo cat "$HOST_CFG/nc-channels-registration.yaml"
```
The registration file now sits on the host at `$HOST_CFG/nc-channels-registration.yaml`, which is visible
INSIDE the Synapse container at `$CTR_CFG/nc-channels-registration.yaml` (that's the path Synapse must load).

---

## STEP 4 — THE CONFIG EDIT (production Synapse — read this section twice before running it)

### 4a. Backup, with the restore command written ABOVE the edit
```bash
BAK="$HOST_CFG/homeserver.yaml.bak-$(date +%s)"
sudo cp "$HOST_CFG/homeserver.yaml" "$BAK" && echo "backed up -> $BAK"
# ── ROLLBACK (copy-paste if anything below goes wrong) ─────────────────────────
#   sudo cp "$BAK" "$HOST_CFG/homeserver.yaml" && ( sudo systemctl restart "$SYN" 2>/dev/null || docker restart "$SYN" )
# ──────────────────────────────────────────────────────────────────────────────
```

### 4b. READ the current `app_service_config_files` and BRANCH on what's actually there
This homeserver has run since April — it may ALREADY register an AS, the key may be absent, or commented.
Do not assume an empty start; clobbering an existing registration breaks whatever is already bridged.
```bash
sudo grep -n "app_service_config_files" "$HOST_CFG/homeserver.yaml" || echo "KEY ABSENT"
# show the block if present:
sudo awk '/app_service_config_files/{f=1} f{print} f&&/^[^ ]/&&!/app_service_config_files/{exit}' "$HOST_CFG/homeserver.yaml"
```
Branch on the output — pick ONE:
- **KEY ABSENT** → append a fresh key (adds only your entry):
  ```bash
  printf '\napp_service_config_files:\n  - %s/nc-channels-registration.yaml\n' "$CTR_CFG" \
    | sudo tee -a "$HOST_CFG/homeserver.yaml" >/dev/null
  ```
- **KEY PRESENT WITH ENTRIES** (e.g. another bridge already listed) → **APPEND to the list, do not replace.**
  Edit by hand and add ONE line under the existing entries, same indentation:
  ```bash
  sudo nano "$HOST_CFG/homeserver.yaml"   # under the existing "- ..." lines add:  - <CTR_CFG>/nc-channels-registration.yaml
  ```
- **KEY PRESENT BUT EMPTY** (`app_service_config_files: []` or bare) → populate it with your one entry
  (replace the empty value only), same as the append form.

### 4c. Verify the edit is well-formed YAML BEFORE restarting (a syntax error here takes Synapse down)
```bash
sudo python3 -c "import yaml,sys; yaml.safe_load(open('$HOST_CFG/homeserver.yaml')); print('YAML OK')" \
  || echo "STOP: YAML broke — restore from \$BAK now, do NOT restart"
# confirm your entry is present exactly once:
sudo grep -c "nc-channels-registration.yaml" "$HOST_CFG/homeserver.yaml"   # expect: 1
```

---

## STEP 5 — restart, then CONFIRM SYNAPSE CAME UP CLEAN before declaring anything live
Edit → restart → confirm-healthy → **rollback-if-not**. Catch "Synapse didn't restart clean" as its own
gate (same lesson as the Fargate task-health check), not when Element can't connect.
```bash
sudo systemctl restart "$SYN" 2>/dev/null || docker restart "$SYN"
sleep 8
# (i) container is running, not crash-looping:
docker ps --filter "name=$SYN" --format '{{.Names}}\t{{.Status}}'
# (ii) no config/startup errors in the last 2 min:
docker logs --since 2m "$SYN" 2>&1 | grep -iE "error|traceback|invalid|failed to load|config" | head
# (iii) it loaded YOUR appservice:
docker logs --since 2m "$SYN" 2>&1 | grep -i "appservice\|application service" | head
# (iv) the public CS-API is serving again (existing traffic unbroken):
curl -sf https://matrix.neuraledge.in/_matrix/client/versions >/dev/null && echo "HEALTHY: CS-API up" || echo "DOWN"
```
**If (i) shows Restarting, (ii) shows a config error, or (iv) says DOWN → ROLLBACK NOW:**
```bash
sudo cp "$BAK" "$HOST_CFG/homeserver.yaml" && ( sudo systemctl restart "$SYN" 2>/dev/null || docker restart "$SYN" )
```
Only proceed past here when (i)–(iv) are all clean.

---

## STEP 6 — run the bridge (containerized on Synapse's docker network so it's reachable at `nc-channels-bar1a:8010`)
```bash
cd ~/neural-ops
docker run -d --name nc-channels-bar1a --network "$NET" --restart unless-stopped \
  --env-file ~/nc-bar1a.env -v "$PWD":/app -w /app \
  python:3.12-slim python3 tools/run_nc_channels_bar1a.py
sleep 2
docker logs nc-channels-bar1a          # expect: "nc-channels serving on 0.0.0.0:8010 (reflect=True) → HS https://matrix.neuraledge.in"
# prove Synapse can REACH the bridge over the network (403 = reached + rejected empty auth = GOOD; connection refused = BAD network/name):
docker exec "$SYN" sh -c "wget -qO- --method=PUT http://nc-channels-bar1a:8010/_matrix/app/v1/transactions/probe 2>&1 || true"
```
A `403 M_FORBIDDEN` from that probe is the **success** signal — Synapse reached the bridge and the bridge
correctly rejected an unauthenticated transaction. "Connection refused"/name-not-resolved = the bridge isn't
on `$NET` or the name differs; fix before Step 7.

---

## STEP 7 — wire a room and verify the echo
Synapse only forwards a room's messages to the AS if a user it's interested in is in that room. The bridge's
own user `@neos-bot:neuraledge.in` isn't in the `@neop_*` namespace, so we put `@neos-bot` in the room and
Synapse becomes interested in it.
```bash
# 7a. In Element: create a room, INVITE @neos-bot:neuraledge.in, and copy the internal room id
#     (Element → room settings → Advanced → "Internal room ID", looks like !abcd...:neuraledge.in)
ROOM='!PASTE_ROOM_ID:neuraledge.in'
# 7b. @neos-bot accepts the invite via the as_token (the AS acts as its sender by default):
set -a; . ~/nc-bar1a.env; set +a
curl -sf -X POST "https://matrix.neuraledge.in/_matrix/client/v3/join/$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$ROOM")" \
  -H "Authorization: Bearer $AS_TOKEN" -H "Content-Type: application/json" -d '{}' && echo " <- @neos-bot joined"
# 7c. In Element, in that room, send:  hello
#     Expected reply from @neos-bot:  echo ⟳ hello
# watch it happen:
docker logs -f nc-channels-bar1a
```
`echo ⟳ hello` appears in Element = **Wire A proven. Bar 1a shipped: transport proven.**

---

## STEP 8 — teardown (leave the box as found; this deployment is meant to be ephemeral)
```bash
docker rm -f nc-channels-bar1a
# remove the registration from homeserver.yaml (restore the pre-edit backup is cleanest):
sudo cp "$BAK" "$HOST_CFG/homeserver.yaml"
sudo rm -f "$HOST_CFG/nc-channels-registration.yaml"
sudo systemctl restart "$SYN" 2>/dev/null || docker restart "$SYN"
curl -sf https://matrix.neuraledge.in/_matrix/client/versions >/dev/null && echo "restored + healthy"
shred -u ~/nc-bar1a.env 2>/dev/null || rm -f ~/nc-bar1a.env
```

---

## Consolidated rollback (any step, any time)
```bash
sudo cp "$BAK" "$HOST_CFG/homeserver.yaml"                 # undo the config edit
sudo systemctl restart "$SYN" 2>/dev/null || docker restart "$SYN"
docker rm -f nc-channels-bar1a 2>/dev/null                 # stop the bridge
curl -sf https://matrix.neuraledge.in/_matrix/client/versions >/dev/null && echo "rolled back + healthy"
```

## Honest success line
> **Bar 1a shipped: transport proven** (Element↔Synapse↔nc-channels round-trip, real production Synapse).
> NOT a working NEop, NOT memory, NOT ranking. Wire B (runtime/M1b + the B-fwd decision) and Wire C
> (palace/GAP-1 + #84 ALB) are still ahead — the first of three wires, the only bridge-only one. Keep the
> #88 framing when the echo lands.
