#!/usr/bin/env bash
# GATE 1 — comms tier / Synapse up.  apply (plan-first, via gate-apply.sh) → VERIFY healthy + server_name → STOP.
# Does ONE gate. Does NOT proceed to AS registration (that's the backup-first runbook, human-in-loop). Re-run
# nothing after this until you've eyeballed the verify below on the LIVE box.
#
# Usage:  ./deploy-1-synapse.sh [extra terraform -var/-var-file args]
#   SYNAPSE_URL=http://<host>:8008  ./deploy-1-synapse.sh      # to auto-check health (else manual)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- apply this gate only (gate-apply is plan-first + typed-confirm + one apply + stop) ---
"$HERE/gate-apply.sh" "comms tier / Synapse" -var 'enable_comms_tier=true' "$@"

echo ""
echo "== VERIFY GATE 1 — Synapse must be HEALTHY and server_name CORRECT before AS registration =="
ok=0
if [ -n "${SYNAPSE_URL:-}" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' "${SYNAPSE_URL%/}/_matrix/client/versions" 2>/dev/null || echo 000)
  if [ "$code" = "200" ]; then echo "  [auto] Synapse client-API responded 200 at $SYNAPSE_URL ✓"; ok=1
  else echo "  [auto] Synapse did NOT return 200 (got $code) at $SYNAPSE_URL — NOT healthy. Stop."; fi
else
  echo "  [manual] SYNAPSE_URL not set — verify by hand: curl <synapse>/_matrix/client/versions → 200."
fi
echo "  [manual — REQUIRED] confirm the baked server_name is exactly 'neuraledge.in' on the live homeserver"
echo "           (it is immutable after first boot; if it's wrong, fix BEFORE registering the AS)."
echo ""
echo "=================================================================================="
echo " GATE 1 done. STOP. Do NOT proceed until: Synapse healthy${SYNAPSE_URL:+ (auto-check $([ $ok = 1 ] && echo PASS || echo FAIL))} AND server_name=neuraledge.in confirmed."
echo " NEXT (separate, conscious): AS registration — docs/deployment/bar1a-box-runbook.md (backup-first, NOT a script)."
echo "=================================================================================="
