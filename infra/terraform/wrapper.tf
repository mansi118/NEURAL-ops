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
# COUPLING — depends on var.wrapper_provider:
#   - amazon-bedrock (DEFAULT/sealed): requires the no-NAT endpoints (aws_security_group.vpce[0] exists only when
#     enable_nat_gateway=false). The model path IS the bedrock-runtime PrivateLink endpoint; sealed egress.
#   - openrouter (opt-in): the INVERSE — requires enable_nat_gateway=true (public gateway needs internet egress),
#     and un-seals the wrapper's egress (EGRESS #1b). The vpce reference is not evaluated in this mode.
# Pick ONE consistently: bedrock↔no-NAT (sealed) OR openrouter↔NAT (un-sealed). A mismatch (openrouter + no-NAT)
# deploys a wrapper that can't reach its model.

# ── secrets: created empty, values set post-apply via `aws secretsmanager put-secret-value` (never in TF
#    state — same posture as secrets.tf / nc-channels.tf). The wrapper CODE refuses to start on a blank
#    FORWARD_TOKEN or blank AWS_BEARER_TOKEN_BEDROCK, so wiring them as REQUIRED secrets means a misconfigured
#    deploy FAILS TO START rather than coming up insecure. Infra and code agree on fail-closed.
# Provider switch (var.wrapper_provider): "amazon-bedrock" (DEFAULT — sealed spine, no NAT) or "openrouter"
# (a PUBLIC gateway — requires enable_nat_gateway=true and UN-SEALS the wrapper's egress; see EGRESS below).
# The runtime code supports both (pi-neop-runtime ModelBroker #8); this only wires the deploy for each.
locals {
  wrapper_is_openrouter = var.wrapper_provider == "openrouter"
  wrapper_model_secret  = local.wrapper_is_openrouter ? "OPENROUTER_API_KEY" : "AWS_BEARER_TOKEN_BEDROCK"
  wrapper_secret_keys   = ["FORWARD_TOKEN", local.wrapper_model_secret]

  # ── MULTI-SEAT (2026-07-09) — one wrapper task per NEop seat, keyed by neop_id. ──────────────────────
  # The per-seat resources (task-def, service, Cloud Map) are for_each'd over this map; the SHARED resources
  # (secrets, SG, log group) stay singletons — every seat uses the same FORWARD_TOKEN + model bearer + jail SG.
  # SAFETY: the FIRST seat MUST keep byte-identical names to the pre-refactor singleton (svc/family
  # "${local.name}-wrapper", DNS "seat-wrapper") so a `terraform state mv [0] -> ["<neop_id>"]` shows it
  # UNCHANGED (never destroy/recreate the live seat a real user is on). Additional seats get suffixed names.
  wrapper_seats = var.enable_wrapper ? merge(
    { (var.wrapper_neop_id) = {
      neop_path  = var.wrapper_neop_path
      svc_name   = "${local.name}-wrapper" # unchanged — the live seat's existing names
      dns_name   = "seat-wrapper"
      log_prefix = "wrapper" # unchanged — keep the live seat's task-def byte-identical
    } },
    var.enable_recon_seat ? { recon = {
      neop_path  = "agents/recon"
      svc_name   = "${local.name}-wrapper-recon"
      dns_name   = "seat-wrapper-recon"
      log_prefix = "recon"
    } } : {}
  ) : {}
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
  # authOk). Held EMPTY by default (fail-closed: no source ⇒ unreachable). Reached over the matrix↔spine
  # peering (peering.tf, §INBOUND resolved); set this to the matrix/bridge CIDR when peering is up.
  dynamic "ingress" {
    for_each = length(var.wrapper_ingress_cidrs) > 0 ? [1] : []
    content {
      description = "POST /seat/turn from the bridge (FORWARD_TOKEN-authenticated) - source scoped, never 0.0.0.0/0"
      from_port   = var.wrapper_port
      to_port     = var.wrapper_port
      protocol    = "tcp"
      cidr_blocks = var.wrapper_ingress_cidrs
    }
  }

  # EGRESS #1a — MODEL (Bedrock, DEFAULT/SEALED): bedrock-runtime via the interface VPC endpoint (443). The
  # vpce SG fronts the bedrock-runtime PrivateLink endpoint (endpoints.tf) — and also secretsmanager/ecr/logs,
  # which the task legitimately needs at launch (secret injection, image pull, logging). Locked to that SG; no
  # internet. This is the sealed-spine path.
  dynamic "egress" {
    for_each = local.wrapper_is_openrouter ? [] : [1]
    content {
      description     = "Bedrock-runtime (model) + secretsmanager/ecr/logs - the VPC interface endpoints, 443 only"
      from_port       = 443
      to_port         = 443
      protocol        = "tcp"
      security_groups = [aws_security_group.vpce[0].id]
    }
  }

  # EGRESS #1c - S3 GATEWAY endpoint (ECR image LAYERS): the manifest comes via the ecr.dkr interface
  # endpoint (#1a), but the layer blobs live in S3 and are pulled at LAUNCH via the S3 gateway endpoint (a
  # prefix-list route, NOT the vpce SG). Without this the task fails CannotPullContainerError. Sealed: the
  # S3 gateway endpoint is in-VPC/private, never the internet - interface-endpoint egress alone is insufficient.
  dynamic "egress" {
    for_each = local.wrapper_is_openrouter ? [] : [1]
    content {
      description     = "S3 gateway endpoint (ECR image layers at launch) - prefix list, 443 only"
      from_port       = 443
      to_port         = 443
      protocol        = "tcp"
      prefix_list_ids = [aws_vpc_endpoint.s3[0].prefix_list_id]
    }
  }

  # EGRESS #1b — MODEL (OpenRouter, OPT-IN, ⚠️ UN-SEALS THE SPINE): openrouter.ai is a PUBLIC gateway, so this
  # opens 443 to the internet (0.0.0.0/0). This is the ONE place the sealed-egress posture is deliberately
  # traded away for simpler provisioning — it REQUIRES enable_nat_gateway=true (no NAT ⇒ unreachable anyway) and
  # it means the wrapper's egress is NO LONGER the GAP-2 jail allowlist {palace, model}. Chosen only when
  # var.wrapper_provider="openrouter". Do NOT default to this; it is the fast-dogfood path, not the sealed one.
  dynamic "egress" {
    for_each = local.wrapper_is_openrouter ? [1] : []
    content {
      description = "OpenRouter (openrouter.ai, PUBLIC) - HTTPS to the internet. UN-SEALED: requires enable_nat_gateway=true"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  # EGRESS #2 — MEMORY: the palace /mcp (CORTEX-PALACE, in-VPC Convex, Cloud Map convex.<ns>:3211). Locked to
  # the convex SG on its API/site-proxy ports. This is the ranked-memory hop (GAP-1).
  egress {
    description     = "Palace /mcp (CORTEX-PALACE, in-VPC Convex) - ranked memory, 3210-3211 only"
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
  for_each = local.wrapper_seats
  name     = each.value.dns_name

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
  for_each                 = local.wrapper_seats
  family                   = each.value.svc_name
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
          { name = "NEOP_PROVIDER", value = var.wrapper_provider },                                                          # amazon-bedrock (sealed) | openrouter (un-sealed)
          { name = "NRT_MODEL", value = local.wrapper_is_openrouter ? var.wrapper_openrouter_model : var.wrapper_model_id }, # per-provider model id
          { name = "AWS_REGION", value = var.region },                                                                       # ap-south-1 (broker also pins it; explicit here)
          { name = "SEAT_PORT", value = tostring(var.wrapper_port) },
          # Bind 0.0.0.0 (not the code default 127.0.0.1) so the bridge reaches /seat/turn over the peering;
          # the wrapper SG ingress (matrix CIDR:port) + FORWARD_TOKEN are the actual access controls.
          { name = "SEAT_HOST", value = "0.0.0.0" },
          { name = "PALACE_MCP_URL", value = var.wrapper_palace_mcp_url }, # in-VPC Cloud Map convex /mcp (internal)
          { name = "PALACE_ID", value = var.wrapper_palace_id },           # scope — from env, never payload
          { name = "NEOP_ID", value = each.key },                          # scope (per-seat) — from env, never payload
          { name = "NEOP_PATH", value = each.value.neop_path },            # the seat's NEop folder (per-seat)
          # Relevance gate for retrieved memory (reply.ts): drop chunks below this palace-similarity score.
          # Measured live 2026-07-09: on-topic ~1.07-1.14, off-topic ~0.19 → 1.0 keeps real hits. 0 = off.
          { name = "SEAT_MEMORY_MIN_SCORE", value = tostring(var.wrapper_memory_min_score) },
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
          "awslogs-stream-prefix" = each.value.log_prefix # per-seat prefix; aria stays "wrapper" (byte-identical)
        }
      }
    },
  ])
}

resource "aws_ecs_service" "wrapper" {
  for_each        = local.wrapper_seats
  name            = each.value.svc_name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.wrapper[each.key].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.wrapper[0].id] # shared jail SG (same egress allowlist for every seat)
    assign_public_ip = false                              # sealed spine — no public IP on the NEop-executing task
  }

  service_registries {
    registry_arn = aws_service_discovery_service.wrapper[each.key].arn
  }
}

# ── §INBOUND — RESOLVED 2026-07-08 toward PEERING (peering.tf). ──────────────────────────────────────────────
# The bridge (nc_channels, Python) runs on the MATRIX-SERVER EC2 BOX (default VPC), so Synapse stays localhost
# (Option B). It reaches this wrapper's /seat/turn over a matrix↔spine VPC PEERING (peering.tf, held on
# var.enable_matrix_peering) — NOT a public ALB. Rationale (sealed spine): a public token-gated ALB is still a
# public surface on the NEop-executing task (authenticated ≠ invisible; internet-reachable, FORWARD_TOKEN the
# only gate). Peering keeps the wrapper unreachable from the internet entirely — symmetric to the egress: no
# 0.0.0.0/0 outbound here, so no public inbound either. (A public ALB stays a deliberate, non-default option if
# ever chosen; it is not built and not defaulted.)
# The two halves: peering.tf gives the ROUTE (both directions); wrapper_ingress_cidrs (set to the matrix/bridge
# CIDR when peering is up) gives the scoped SG ALLOWANCE. Default [] ⇒ UNREACHABLE until peering + the var are
# set together in the deploy window. The whole inbound path is now in code (held), so the apply gate has it all.
