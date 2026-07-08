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
