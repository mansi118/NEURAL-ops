---
neop_id: aws-probe
version: 1
role_family: executor
model: { executor: stub }
limits: { max_replans: 0 }
tools: [sts_whoami]
acp: { publishes: [aws_identity] }
---
# AWS Probe NEop
Pure executor (role_family=executor -> [EXECUTE] only). Calls one read-only AWS
tool (`sts_whoami`) and publishes the caller identity. Proves AWS is wired into
the NEOS tool layer: declared in the allowlist, deterministic in unit mode via a
mock, live via `runtime.aws` in integration mode.
