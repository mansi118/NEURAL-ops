#!/usr/bin/env bash
# dogfish_acl_smoke.sh
# The one USER-gated proof convex-test can only simulate: a live cross-seat ACL
# denial against the dogfish deployment. Green = Day-90 zero-violation clock starts.
#
# SECURITY: reads NO secrets inline. The Convex deploy key must already be in your
# env (CONVEX_DEPLOY_KEY) or via `npx convex login`. Never paste a key into this
# file, the repo, or a PR.
#
# CROSS-REPO REALITY (verified 2026-06-18): the four steps span TWO repos.
#   - Steps 1-3 (deploy + both seeds) live in Mempalace_NEOS (Convex backend).
#   - Step 4 (the python smoke, tools/dogfish_acl_smoke.py) lives in NEURAL-ops,
#     i.e. THIS repo, on branch feat/dogfish-acl-smoke.
# This driver runs each step in its correct repo; it does not assume one root.
# Run it from anywhere — paths resolve off the script's own location.

set -euo pipefail

# ---- config -----------------------------------------------------------------
DEPLOYMENT="${DEPLOYMENT:-small-dogfish-433}"
CONVEX_CLOUD_URL="https://${DEPLOYMENT}.convex.cloud"   # seeds talk here (.cloud, CONVEX_URL)
CONVEX_SITE_URL="https://${DEPLOYMENT}.convex.site"     # /mcp HTTP actions live here (.site)

# NEURAL-ops repo root = the dir above this script (tools/..). The python smoke is here.
NEURALOPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE="$NEURALOPS_DIR/tools/dogfish_acl_smoke.py"

# Mempalace_NEOS (Convex backend) holds deploy + seeds. Override with MEMPALACE_DIR=...
MEMPALACE_DIR="${MEMPALACE_DIR:-$(cd "$NEURALOPS_DIR/.." && pwd)/Mempalace_NEOS}"

WING="${WING:-team}"        # a wing both seats may operate in (aria writes team; recon just owns a room)
SEAT_A="${SEAT_A:-aria}"
SEAT_B="${SEAT_B:-recon}"
# Pre-set to skip the auto-parse:  PALACE_ID=<id> ./dogfish_acl_smoke.sh
PALACE_ID="${PALACE_ID:-}"

banner() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
die()    { printf '\n\033[1;31mFAIL: %s\033[0m\n' "$*" >&2; exit 1; }

# ---- 0. prereqs -------------------------------------------------------------
banner "0/4  prereqs"
command -v npx     >/dev/null || die "npx not found"
command -v npm     >/dev/null || die "npm not found"
command -v python3 >/dev/null || die "python3 not found"
[[ -f "$SMOKE" ]]                     || die "missing smoke: $SMOKE"
[[ -d "$MEMPALACE_DIR/convex" ]]      || die "Mempalace_NEOS not found at $MEMPALACE_DIR (set MEMPALACE_DIR=...)"
[[ -f "$MEMPALACE_DIR/scripts/seedAccess.ts" ]] || die "missing $MEMPALACE_DIR/scripts/seedAccess.ts"
if [[ -z "${CONVEX_DEPLOY_KEY:-}" ]]; then
  echo "note: CONVEX_DEPLOY_KEY unset — relying on \`npx convex login\` session."
  echo "      if step 1 fails on auth, export the deploy key and re-run."
fi
echo "neuralops repo    : $NEURALOPS_DIR"
echo "mempalace repo    : $MEMPALACE_DIR"
echo "target deployment : $DEPLOYMENT"
echo "  cloud (seeds)   : $CONVEX_CLOUD_URL"
echo "  site  (/mcp)    : $CONVEX_SITE_URL"
echo "seats             : A=$SEAT_A  B=$SEAT_B   wing=$WING"

# ---- 1. deploy (in Mempalace_NEOS) ------------------------------------------
banner "1/4  npx convex deploy → $DEPLOYMENT   (in Mempalace_NEOS)"
( cd "$MEMPALACE_DIR" && npx convex deploy )

# ---- 2. seed palace, capture palaceId (in Mempalace_NEOS) -------------------
banner "2/4  npm run seed:palace   (in Mempalace_NEOS)"
if [[ -n "$PALACE_ID" ]]; then
  echo "PALACE_ID pre-set ($PALACE_ID) — skipping seed parse."
else
  # seedPalace.ts prints exactly:  "  palace: <id>"  (NOT "palaceId: ...").
  seed_out="$( cd "$MEMPALACE_DIR" && CONVEX_URL="$CONVEX_CLOUD_URL" npm run --silent seed:palace 2>&1 | tee /dev/stderr )"
  PALACE_ID="$(printf '%s\n' "$seed_out" | awk '/palace:/{print $NF}' | tail -n1)"
  [[ -n "$PALACE_ID" ]] || die "couldn't parse palaceId from seed output. Grab it manually and re-run:  PALACE_ID=<id> $0"
fi
echo "palaceId = $PALACE_ID"

# ---- 3. seed access matrix (neop_permissions ← access_matrix.yaml) ----------
banner "3/4  npm run seed:access → neop_permissions   (in Mempalace_NEOS)"
( cd "$MEMPALACE_DIR" && CONVEX_URL="$CONVEX_CLOUD_URL" npm run --silent seed:access )

# ---- 4. fire the cross-seat ACL smoke (NEURAL-ops, hits /mcp on .convex.site) ----
banner "4/4  cross-seat ACL smoke   (NEURAL-ops → $CONVEX_SITE_URL/mcp)"
set +e
CONVEX_SITE_URL="$CONVEX_SITE_URL" python3 "$SMOKE" \
  --palace "$PALACE_ID" --seat-a "$SEAT_A" --seat-b "$SEAT_B" --wing "$WING"
rc=$?
set -e

if [[ $rc -eq 0 ]]; then
  printf '\n\033[1;32mPASS — cross-seat denial proven live. Day-90 zero-violation clock is GO.\033[0m\n'
else
  printf '\n\033[1;31mSMOKE FAILED (exit %d). Clock does NOT start.\033[0m\n' "$rc"
  echo "check first: did BOTH seeds run against .cloud while the smoke hit .site? (the gotcha)"
fi
exit $rc
