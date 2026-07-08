#!/usr/bin/env bash
# gate-apply.sh — ONE terraform gate: plan-first, typed-confirm, one apply, then STOP.
#
# This script deliberately does exactly ONE apply and then stops. It does NOT chain to the next gate, does NOT
# register the AS, does NOT touch T9. Re-run it per gate with that gate's vars. Collapsing gates into one run is
# the anti-pattern this whole directory exists to prevent (see README.md).
#
# Usage:
#   ./gate-apply.sh "<gate label>" <terraform apply/plan args...>
# Examples:
#   ./gate-apply.sh "comms tier / Synapse" -var 'enable_comms_tier=true'
#   ./gate-apply.sh "wrapper" -var 'enable_wrapper=true' -var 'enable_matrix_peering=true' \
#                             -var 'wrapper_ingress_cidrs=["10.0.0.0/16"]'
#   # or with a var-file:  ./gate-apply.sh "comms tier" -var-file=phase2.tfvars
#
# Runs against infra/terraform. Assumes you are on LEAST-PRIVILEGE creds (admin scoped off this box — README §0).

set -euo pipefail

GATE="${1:-}"
if [ -z "$GATE" ]; then echo "usage: $0 \"<gate label>\" <terraform args...>" >&2; exit 2; fi
shift
if [ "$#" -eq 0 ]; then echo "refusing: no terraform vars given for gate '$GATE'" >&2; exit 2; fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(cd "$HERE/../terraform" && pwd)"
PLAN_OUT="$(mktemp -t gate-plan.XXXXXX.tfplan)"
trap 'rm -f "$PLAN_OUT"' EXIT

echo "== GATE: $GATE =="
echo "   terraform dir: $TF_DIR"
echo "   caller identity (confirm this is SCOPED, not admin):"
aws sts get-caller-identity --query '{account:Account,arn:Arn}' --output table 2>&1 | sed 's/^/     /' || true
echo ""

echo "== 1/3 PLAN (read this in full) =="
( cd "$TF_DIR" && terraform plan -out="$PLAN_OUT" "$@" )

echo ""
echo "== 2/3 CONFIRM =="
echo "   Review the plan above. It should touch ONLY the '$GATE' resources — nothing in the live runtime spine"
echo "   you didn't intend, correct account (071126865245), no destroys you didn't expect."
printf "   Type exactly APPLY to proceed (anything else aborts): "
read -r ANS
if [ "$ANS" != "APPLY" ]; then echo "   aborted — no changes made."; exit 1; fi

echo ""
echo "== 3/3 APPLY (this gate only) =="
( cd "$TF_DIR" && terraform apply "$PLAN_OUT" )

echo ""
echo "=================================================================================="
echo " GATE '$GATE' APPLIED. This script STOPS here — it does NOT proceed to the next gate."
echo ""
echo " VERIFY ON THE LIVE BOX before the next gate (see infra/deploy/README.md):"
echo "   - comms tier / Synapse  → Synapse healthy + server_name=neuraledge.in"
echo "   - wrapper               → wrapper task healthy + reaches palace /mcp + the model endpoint"
echo ""
echo " NEXT gate is a SEPARATE, CONSCIOUS run — and remember AS-registration is the runbook (not a script),"
echo " the four box proofs come before T9, and T9 (wrapper_t9_ack=true) is its own deliberate crossing."
echo "=================================================================================="
