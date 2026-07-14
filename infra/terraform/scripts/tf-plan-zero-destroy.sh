#!/usr/bin/env bash
# tf-plan-zero-destroy.sh — the plan-first, zero-destroy gate the plan calls for before applying the
# flag-gated schedulers (Step 2.4) or any other additive change. Runs `terraform plan` with the vars you
# pass through, then FAILS if the plan would DELETE (or replace) any resource. A clean pass proves the
# change is purely additive against live — the same discipline that caught the SEAT_MEMORY_MIN_SCORE drift.
#
# Usage (extra args pass straight to terraform plan):
#   infra/terraform/scripts/tf-plan-zero-destroy.sh \
#     -var enable_fidelity_scheduler=true -var enable_vault_scheduler=true \
#     -var fidelity_palace_id=... -var fidelity_convex_url=... -var vault_seats=aria,recon
#
# On zero destroys: prints the add/change counts and exits 0 (then you run `terraform apply <same vars>`).
# On any destroy/replace: prints the offending resources and exits 1 — DO NOT apply.
set -euo pipefail

TF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TF_DIR"

PLAN_FILE="$(mktemp -t tfplan.XXXXXX)"
trap 'rm -f "$PLAN_FILE" "$PLAN_FILE.json"' EXIT

echo ">> terraform plan (args: $*)"
terraform plan -input=false -out="$PLAN_FILE" "$@"

terraform show -json "$PLAN_FILE" > "$PLAN_FILE.json"

if command -v jq >/dev/null 2>&1; then
  destroys="$(jq '[.resource_changes[]? | select(.change.actions | (index("delete") or index("replace")))] | length' "$PLAN_FILE.json")"
  destroyed="$(jq -r '.resource_changes[]? | select(.change.actions | (index("delete") or index("replace"))) | .address' "$PLAN_FILE.json")"
else
  echo "!! jq not found — falling back to the plan summary line (less precise)"
  destroys="$(terraform show "$PLAN_FILE" | grep -Eo '[0-9]+ to destroy' | grep -Eo '^[0-9]+' || echo 0)"
  destroyed=""
fi

if [[ "${destroys:-0}" -ne 0 ]]; then
  echo "!! ZERO-DESTROY GATE FAILED: plan would delete/replace ${destroys} resource(s):"
  echo "${destroyed}" | sed 's/^/     - /'
  echo "!! This is NOT additive against live. Do NOT apply until the plan shows 0 to destroy."
  exit 1
fi

echo "OK zero-destroy gate passed — the plan is additive (0 to destroy/replace)."
echo "   Review the add/change list above, then: terraform apply $*"
