# Secrets Manager: one secret per required key, created EMPTY. Values are set out-of-band after apply
# (`aws secretsmanager put-secret-value ...`) so a credential never enters TF code or state — the
# code-side analog of runtime/secrets.py (env→keyring→refuse) and the S0.2 posture.

resource "aws_secretsmanager_secret" "runtime" {
  for_each = toset(var.managed_secret_keys)

  name        = "${local.name}/${each.value}"
  description = "${each.value} for the NEOS runtime (value set post-apply, never in TF state)."
  kms_key_id  = aws_kms_key.main.arn
  tags        = { Name = "${local.name}-${lower(each.value)}" }
}
