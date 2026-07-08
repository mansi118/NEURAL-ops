# nc-channels — RETIRED as a spine-VPC Fargate service (2026-07-08, deploy-topology Decision 2 / Option B).
#
# WHY RETIRED (structural, not a stale comment): this file used to define a spine-VPC Fargate service for the
# nc_channels Matrix Application-Service bridge, with a `0.0.0.0/0` egress SG and an ingress from the (now
# also-superseded) Fargate Synapse SG (aws_security_group.synapse). That topology is SUPERSEDED:
#   - Decision 2 splits the runtime into THREE components (deploy-topology-design.md): the nc_channels BRIDGE
#     (Python), the Hermes seat WRAPPER (Node, → wrapper.tf), and the palace. Under Option B the **bridge runs
#     on the matrix-server EC2 box** (default VPC), so Synapse stays localhost and there is no cross-boundary
#     hop except the authenticated bridge→wrapper forward. The bridge is therefore NOT a spine Fargate service
#     and is NOT managed by this terraform — it is provisioned on the matrix box (process/systemd/docker).
#   - The retired SG carried a `0.0.0.0/0` egress. The new NEop-executing surface (wrapper.tf) locks egress to
#     exactly {bedrock endpoint, palace} — that widening must NOT come back. Removing the resources here (rather
#     than leaving them count-gated) means the stale posture cannot be resurrected by flipping a flag.
#
# The resources are removed structurally (they were count/for_each-gated on var.enable_nc_channels, default
# false, and were never applied — no state to orphan; verified referenced only within this file). The
# variables (enable_nc_channels / nc_channels_image / nc_channels_port) remain in variables.tf, harmless and
# unused; left in place to avoid churn. If a spine-side bridge is ever wanted again, author it fresh against
# the CURRENT topology (locked egress, no 0.0.0.0/0) — do not restore this retired shape.
#
# See: wrapper.tf (the seat wrapper that replaces the runtime concern), deploy-topology-design.md (§Option B),
# and the bridge's box placement in the Bar-1a / nc-channels-placement runbooks.
