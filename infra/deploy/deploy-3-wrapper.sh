#!/usr/bin/env bash
# GATE 3 — wrapper live in-spine.  apply (plan-first, via gate-apply.sh) → VERIFY reachability → STOP.
# Does ONE gate. Does NOT run the box proofs (4-7) and does NOT touch T9 (8). Those are separate conscious runs.
#
# PRE-REQ: gates 1 (Synapse healthy) and 2 (AS registered, runbook) done + verified first.
# Usage:  ./deploy-3-wrapper.sh -var 'wrapper_ingress_cidrs=["<matrix-cidr>"]' [more -var/-var-file args]
#   CLUSTER=neos-dogfood-cluster  WRAPPER_SVC=neos-dogfood-wrapper  ./deploy-3-wrapper.sh ...   # to auto-check ECS
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- apply this gate only (plan-first, typed-confirm, one apply, stop) ---
# NOTE: wrapper_provider + enable_matrix_peering + model choice come from your tfvars/-var args (see wrapper.tf).
"$HERE/gate-apply.sh" "wrapper" -var 'enable_wrapper=true' "$@"

echo ""
echo "== VERIFY GATE 3 — wrapper must be HEALTHY and REACH palace + model before any box proof =="
CLUSTER="${CLUSTER:-neos-dogfood-cluster}"; WRAPPER_SVC="${WRAPPER_SVC:-neos-dogfood-wrapper}"
run=$(aws ecs describe-services --cluster "$CLUSTER" --services "$WRAPPER_SVC" \
        --query 'services[0].{running:runningCount,desired:desiredCount,status:status}' --output text 2>/dev/null || echo "NA NA NA")
echo "  [auto] ECS $WRAPPER_SVC → $run  (want: running==desired, ACTIVE, and not crash-looping)"
echo "  [manual — REQUIRED, in-VPC] confirm the wrapper task reaches:"
echo "     - palace /mcp (convex.<ns>:3211)          — memory hop"
echo "     - the model endpoint (bedrock-runtime PrivateLink, or openrouter if un-sealed) — model hop"
echo "     and check the task log: 'serve-seat' should be REFUSING (no NEOP_T9_ACK yet) — that's correct pre-T9."
echo ""
echo "=================================================================================="
echo " GATE 3 done. STOP. Next are the FOUR BOX PROOFS, each its own run, each green before the next:"
echo "   Bar 1a (transport) → B (ranked memory, seat-approval) → A2 (injection) → GAP-2 (jail)"
echo "   → see docs/deployment/box-proofs-A-B-card.md + bar2-first-live-turn-runbook.md."
echo " T9 (wrapper_t9_ack=true) is the LAST separate conscious crossing, only after all four are green."
echo "=================================================================================="
