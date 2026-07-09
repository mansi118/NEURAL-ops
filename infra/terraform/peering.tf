# peering — matrix-box (default VPC) ↔ spine VPC. The INBOUND path for the bridge → wrapper /seat/turn hop
# (deploy-topology §INBOUND, RESOLVED 2026-07-08 toward PEERING, not a public ALB). AUTHORED-BUT-HELD on
# var.enable_matrix_peering (default false); merging changes nothing live.
#
# WHY PEERING over a public token-gated ALB (the sealed-spine posture): a public ALB — even FORWARD_TOKEN-
# gated — is a public surface on the NEop-executing task. Authenticated ≠ invisible: it is internet-reachable
# and the token is the only thing between the public and /seat/turn. Peering keeps the wrapper unreachable from
# the internet entirely; the bridge reaches it over the peered internal path. Symmetric to the egress: we don't
# open 0.0.0.0/0 OUTBOUND on the wrapper (wrapper.tf), so we don't open a public INBOUND either.
#
# The matrix box's default VPC is NOT managed by this terraform (separate EC2 box), so its id/cidr/route-table
# arrive as VARIABLES (required-together when enabling). Assumes SAME account + region (ap-south-1); if the
# matrix box is in another region, add peer_region + an aws_vpc_peering_connection_accepter (flagged, not built).
#
# TWO HALVES, both required, both scoped, neither public:
#   - ROUTE  (this file + network.tf's inline spine route) — the network path both directions.
#   - ALLOWANCE (wrapper.tf) — set var.wrapper_ingress_cidrs to the bridge's source (the matrix/bridge CIDR)
#     so the wrapper SG admits the bridge on :8090 over the peered path. The peering gives reachability; the
#     SG ingress is still a scoped allowance, never 0.0.0.0/0.

resource "aws_vpc_peering_connection" "matrix" {
  count       = var.enable_matrix_peering ? 1 : 0
  vpc_id      = aws_vpc.main.id   # requester = spine
  peer_vpc_id = var.matrix_vpc_id # accepter  = matrix-box default VPC
  auto_accept = true              # same account + region → auto-accept (no separate accepter resource)
  tags        = { Name = "${local.name}-matrix-peering" }
}

# Matrix → spine route: on the matrix box's route table (external — a standalone aws_route is fine here, no
# inline-route conflict because that table is not a terraform aws_route_table resource in this config).
resource "aws_route" "matrix_to_spine" {
  count                     = var.enable_matrix_peering && var.matrix_route_table_id != "" ? 1 : 0
  route_table_id            = var.matrix_route_table_id
  destination_cidr_block    = var.vpc_cidr # the spine CIDR (10.40.0.0/16)
  vpc_peering_connection_id = aws_vpc_peering_connection.matrix[0].id
}

# (The spine → matrix return route is inline on aws_route_table.private in network.tf — it MUST be inline
#  there, since that table uses inline routes and mixing with a standalone aws_route overwrites rules.)

# ── DURABLE bridge→wrapper wiring (Bar-2 loose-end (b), 2026-07-09). ──────────────────────────────────
# The wrapper is Cloud-Map registered as seat-wrapper.<project>-<env>.local (wrapper.tf), whose A record
# auto-follows the ECS task on every redeploy. But the backing Route53 private hosted zone is associated
# with ONLY the spine VPC, so the bridge (on the matrix box, in the peered matrix VPC) cannot resolve that
# name — which is why Bar 2 shipped with SEAT_URL pinned to the wrapper's *dynamic* task IP (10.40.53.174),
# a wire that breaks the instant the wrapper task is replaced.
#
# Associating the same hosted zone with the matrix VPC makes seat-wrapper.<project>-<env>.local resolvable
# from the bridge over the existing peering. Then SEAT_URL becomes a STABLE name and survives wrapper
# redeploys (Cloud Map updates the A record; the bridge just follows). Both VPCs are same-account/same-region
# (071126865245 / ap-south-1) → a single association resource, no cross-account authorization dance. The
# matrix VPC has enableDnsSupport + enableDnsHostnames = true (verified), which PHZ resolution requires.
#
# Additive + reversible + no data path touched. Gated on the same enable_matrix_peering flag: it is only
# meaningful once the route + peering exist, and it tears down cleanly by flipping the flag.
resource "aws_route53_zone_association" "matrix_wrapper_discovery" {
  count   = var.enable_matrix_peering ? 1 : 0
  zone_id = aws_service_discovery_private_dns_namespace.main.hosted_zone
  vpc_id  = var.matrix_vpc_id
}
