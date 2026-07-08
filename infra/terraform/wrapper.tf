# wrapper — the Hermes seat wrapper (pi-neop-runtime, Node): POST /seat/turn → classify → reply/task →
# palace + model. The NEop-executing component. Runs IN THE SPINE VPC (Decision 2 / deploy-topology-design.md
# §"Option B") because it calls the palace /mcp, which is internal to the spine. AUTHORED-BUT-HELD on
# var.enable_wrapper (default false) — same posture as nc-channels.tf and synapse.tf: present on main, inert
# until a conscious flip. Merging this changes NOTHING live (plan against main shows zero wrapper resources).
#
# WHY HELD: (1) the seat refuses to start without FORWARD_TOKEN (fail-closed, wrapper.ts assertWrapperConfig)
# and refuses to wire live brokers without NEOP_T9_ACK=yes (seat/server.ts) — so a deploy before those are
# provisioned + T9 is crossed is a task that refuses-then-restarts by design. (2) The bridge→wrapper INBOUND
# reach is an open topology decision (see §INBOUND below) — no matrix↔spine VPC peering exists today.
#
# THE TWO GATES, kept distinct at the infra layer (mirroring the code):
#   - enable_wrapper  → deploy the service at all (held false).
#   - wrapper_t9_ack  → set NEOP_T9_ACK=yes, i.e. CROSS T9 (held false). Deploying with this false means the
#     task boots and REFUSES to serve live — the T9 gate holds even against an accidental deploy. Flipping it
#     true is the conscious first-live-turn crossing, plan-first, in the T9 window. Flip both together.
#
# COUPLING (intentional, like nc-channels↔synapse): requires the no-NAT endpoints (aws_security_group.vpce[0]
# only exists when enable_nat_gateway=false). The wrapper's whole model path IS the bedrock-runtime PrivateLink
# endpoint; a NAT'd spine is a different (rejected) topology.

# ── secrets: created empty, values set post-apply via `aws secretsmanager put-secret-value` (never in TF
#    state — same posture as secrets.tf / nc-channels.tf). The wrapper CODE refuses to start on a blank
#    FORWARD_TOKEN or blank AWS_BEARER_TOKEN_BEDROCK, so wiring them as REQUIRED secrets means a misconfigured
#    deploy FAILS TO START rather than coming up insecure. Infra and code agree on fail-closed.
locals {
  wrapper_secret_keys = ["FORWARD_TOKEN", "AWS_BEARER_TOKEN_BEDROCK"]
}

resource "aws_secretsmanager_secret" "wrapper" {
  for_each = var.enable_wrapper ? toset(local.wrapper_secret_keys) : toset([])

  name        = "${local.name}/WRAPPER_${each.value}"
  description = "${each.value} for the Hermes seat wrapper (value set post-apply, never in TF state)."
  kms_key_id  = aws_kms_key.main.arn
  tags        = { Name = "${local.name}-wrapper-${lower(each.value)}" }
}

# ── the wrapper's security group — the SEALED-SPINE ENFORCEMENT at the network layer. This is the GAP-2 jail
#    egress allowlist expressed as infra (isolation.py::egress_allowlist = {palace, model}); the SG and the
#    jail MUST agree — the same two destinations, defense-in-depth. There is DELIBERATELY no 0.0.0.0/0 egress
#    (that is the stale posture nc-channels.tf carried and this topology retires — do NOT reintroduce it "to
#    make it work"; a widened egress is a hole in the sealed spine). Each rule states WHY it exists so a
#    future edit cannot widen it without seeing what it widens.
resource "aws_security_group" "wrapper" {
  count       = var.enable_wrapper ? 1 : 0
  name        = "${local.name}-wrapper-sg"
  description = "Hermes seat wrapper: /seat/turn ingress from the bridge; egress ONLY to {bedrock endpoint, palace}."
  vpc_id      = aws_vpc.main.id

  # INBOUND — the bridge → wrapper /seat/turn hop, authenticated by FORWARD_TOKEN (constant-time, wrapper.ts
  # authOk). Held EMPTY by default (fail-closed: no source ⇒ unreachable). See §INBOUND below for why this is
  # a var and not a fixed source: the bridge is on the matrix box (default VPC) and no peering exists yet.
  dynamic "ingress" {
    for_each = length(var.wrapper_ingress_cidrs) > 0 ? [1] : []
    content {
      description = "POST /seat/turn from the bridge (FORWARD_TOKEN-authenticated) — source scoped, never 0.0.0.0/0"
      from_port   = var.wrapper_port
      to_port     = var.wrapper_port
      protocol    = "tcp"
      cidr_blocks = var.wrapper_ingress_cidrs
    }
  }

  # EGRESS #1 — MODEL: bedrock-runtime via the interface VPC endpoint (443). The vpce SG fronts the
  # bedrock-runtime PrivateLink endpoint (endpoints.tf) — and also secretsmanager/ecr/logs, which the task
  # legitimately needs at launch (secret injection, image pull, logging). Locked to that SG; no internet.
  egress {
    description     = "Bedrock-runtime (model) + secretsmanager/ecr/logs — the VPC interface endpoints, 443 only"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.vpce[0].id]
  }

  # EGRESS #2 — MEMORY: the palace /mcp (CORTEX-PALACE, in-VPC Convex, Cloud Map convex.<ns>:3211). Locked to
  # the convex SG on its API/site-proxy ports. This is the ranked-memory hop (GAP-1).
  egress {
    description     = "Palace /mcp (CORTEX-PALACE, in-VPC Convex) — ranked memory, 3210-3211 only"
    from_port       = 3210
    to_port         = 3211
    protocol        = "tcp"
    security_groups = [aws_security_group.convex.id]
  }

  # NOTE — NO Synapse egress. The wrapper returns the ReplyEnvelope in the HTTP RESPONSE to the bridge's
  # /seat/turn POST; the BRIDGE (on the matrix box) does the CS-API reply_send to Synapse. So the wrapper's
  # egress is exactly {model, palace} = 2 — matching isolation.py::egress_allowlist EXACTLY. Adding a Synapse
  # egress here would make the SG WIDER than the jail allowlist; it is intentionally absent.

  tags = { Name = "${local.name}-wrapper-sg" }
}

# ── service discovery — seat-wrapper.${local.name}.local:${wrapper_port}. Internal (Cloud Map) only; the
#    wrapper has NO public surface (the sealed-spine intent). See §INBOUND for how the bridge reaches this.
resource "aws_service_discovery_service" "wrapper" {
  count = var.enable_wrapper ? 1 : 0
  name  = "seat-wrapper"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_cloudwatch_log_group" "wrapper" {
  count             = var.enable_wrapper ? 1 : 0
  name              = "/ecs/${local.name}-wrapper"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_ecs_task_definition" "wrapper" {
  count                    = var.enable_wrapper ? 1 : 0
  family                   = "${local.name}-wrapper"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name         = "wrapper"
      image        = var.wrapper_image # the pi-neop-runtime GAP-2 jail image (ECR, pulled in-VPC via the ECR endpoint)
      essential    = true
      command      = ["serve-seat"] # nrt serve-seat — POST /seat/turn (seat/server.ts); refuses without FORWARD_TOKEN + T9 ack
      portMappings = [{ containerPort = var.wrapper_port, protocol = "tcp" }]

      # Non-secret env. Scope (PALACE_ID/NEOP_ID) is BAKED FROM ENV, never from the request payload
      # (wrapper.ts rejects M_SCOPE_SPOOF). NEOP_T9_ACK is added ONLY when wrapper_t9_ack=true — the crossing.
      environment = concat(
        [
          { name = "NEOP_PROVIDER", value = "amazon-bedrock" }, # Decision 2 — sealed-spine model
          { name = "NRT_MODEL", value = var.wrapper_model_id }, # apac.amazon.nova-lite-v1:0 (parameterized)
          { name = "AWS_REGION", value = var.region },          # ap-south-1 (broker also pins it; explicit here)
          { name = "SEAT_PORT", value = tostring(var.wrapper_port) },
          { name = "PALACE_MCP_URL", value = var.wrapper_palace_mcp_url }, # in-VPC Cloud Map convex /mcp (internal)
          { name = "PALACE_ID", value = var.wrapper_palace_id },           # scope — from env, never payload
          { name = "NEOP_ID", value = var.wrapper_neop_id },               # scope — from env, never payload
          { name = "NEOP_PATH", value = var.wrapper_neop_path },           # the seat's NEop folder
        ],
        var.wrapper_t9_ack ? [{ name = "NEOP_T9_ACK", value = "yes" }] : [] # T9 CROSSING — held false
      )

      # Required secrets (references only — values never in TF state). Blank ⇒ the wrapper refuses to start.
      secrets = [for k in local.wrapper_secret_keys : { name = k, valueFrom = aws_secretsmanager_secret.wrapper[k].arn }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.wrapper[0].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "wrapper"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "wrapper" {
  count           = var.enable_wrapper ? 1 : 0
  name            = "${local.name}-wrapper"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.wrapper[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.wrapper[0].id]
    assign_public_ip = false # sealed spine — no public IP on the NEop-executing task
  }

  service_registries {
    registry_arn = aws_service_discovery_service.wrapper[0].arn
  }
}

# ── §INBOUND (the one open topology decision — NOT resolved here, deliberately) ─────────────────────────────
# The bridge (nc_channels, Python) runs on the MATRIX-SERVER EC2 BOX (default VPC), so Synapse stays localhost
# (Option B). It must reach this wrapper's /seat/turn. Verified 2026-07-08: there is NO matrix↔spine VPC
# peering. So the reach is an open call, and this file does NOT silently open a public surface to resolve it:
#   (a) VPC peering matrix↔spine + set var.wrapper_ingress_cidrs to the bridge's source — internal, no public
#       surface (the sealed-spine-preserving option; recommended), OR
#   (b) an INTERNAL token-gated ALB + peering (adds a stable endpoint; same peering prerequisite), OR
#   (c) a PUBLIC token-gated ALB — rejected unless deliberately chosen: it puts a public surface on the
#       NEop-executing task, gated only by FORWARD_TOKEN. Contradicts the sealed-spine intent; do NOT default here.
# wrapper_ingress_cidrs defaults to [] ⇒ the wrapper is UNREACHABLE until this is consciously decided. That is
# the honest held state: the egress lockdown is complete and reviewable; the inbound is a named decision, not a
# silent public hole. Resolve it in the deploy window (peering is the recommended path), then set the var.
