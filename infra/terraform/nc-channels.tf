# nc-channels — the Matrix Application-Service transport (D2 = its own ECS service, off the runtime's
# failure domain). AUTHORED-BUT-HELD: everything here is gated on var.enable_nc_channels (default false).
#
# WHY HELD (do not flip casually): nc_channels/service.py:119/125 (serve() / _cs_api_call) still raise
# NotImplementedError by design — their correctness is defined by the LIVE Synapse handshake and is proven
# at the box, never against a mock (transport-deploy-design.md D1; test_live_wire_is_box_gated stays green).
# Deploying this service before that transport is hand-proven = a crash-looping task. The live-window order
# is: hand-drive _cs_api_call against real Synapse → wrap in serve() → THEN flip enable_nc_channels=true and
# apply this file. Box-process first (prove the handshake), ECS service second (make it durable).
#
# OPEN SEAM this file deliberately does NOT paper over: orchestrator.handle() calls runtime.core.dispatch()
# IN-PROCESS (frontdoor/orchestrator.py:104). So this container is NOT a thin transport — it carries the
# frontdoor + runtime and needs the runtime's LLM/palace credentials + palace egress, exactly like the
# runtime task. If the box session instead splits the orchestrator into a separately-reachable service, the
# image + secrets + egress below shrink. That split is a box/design call; until then this mirrors the
# runtime's needs. Named here so it is a decision, not a surprise.
#
# Requires enable_comms_tier=true (references the Synapse SG). Flipping enable_nc_channels without the comms
# tier will fail on the aws_security_group.synapse[0] index — that coupling is intentional.

locals {
  nc_channels_secret_keys = ["AS_TOKEN", "HS_TOKEN", "ADAPTER_HMAC_KEY"]
}

# The three AS secrets (created empty; values set post-apply via `aws secretsmanager put-secret-value`,
# never in TF state — same posture as secrets.tf). These must MATCH the tokens in the registration YAML the
# homeserver loads (transport-deploy-design 3c: tokens → registration file on EFS → homeserver.yaml → restart).
resource "aws_secretsmanager_secret" "nc_channels" {
  for_each = var.enable_nc_channels ? toset(local.nc_channels_secret_keys) : toset([])

  name        = "${local.name}/${each.value}"
  description = "${each.value} for nc-channels AS (value set post-apply, never in TF state)."
  kms_key_id  = aws_kms_key.main.arn
  tags        = { Name = "${local.name}-${lower(each.value)}" }
}

resource "aws_security_group" "nc_channels" {
  count       = var.enable_nc_channels ? 1 : 0
  name        = "${local.name}-nc-channels-sg"
  description = "AS transaction ingress from Synapse only; egress to Synapse CS-API + palace over TLS."
  vpc_id      = aws_vpc.main.id

  # HS→AS: Synapse PUTs transactions to this port. Ingress from the Synapse SG ONLY (D2 — narrow surface).
  ingress {
    description     = "AS transactions from Synapse"
    from_port       = var.nc_channels_port
    to_port         = var.nc_channels_port
    protocol        = "tcp"
    security_groups = [aws_security_group.synapse[0].id]
  }

  # AS→HS reply_send (CS-API :8008, already allowed by synapse-sg's in-VPC ingress) + palace /mcp over TLS.
  egress {
    description = "Synapse CS-API + palace (Convex .site) over TLS"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-nc-channels-sg" }
}

resource "aws_service_discovery_service" "nc_channels" {
  count = var.enable_nc_channels ? 1 : 0
  name  = "nc-channels" # → nc-channels.${local.name}.local:<port> — the `url` baked into the AS registration

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

resource "aws_cloudwatch_log_group" "nc_channels" {
  count             = var.enable_nc_channels ? 1 : 0
  name              = "/ecs/${local.name}-nc-channels"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_ecs_task_definition" "nc_channels" {
  count                    = var.enable_nc_channels ? 1 : 0
  family                   = "${local.name}-nc-channels"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name         = "nc-channels"
      image        = var.nc_channels_image
      essential    = true
      portMappings = [{ containerPort = var.nc_channels_port, protocol = "tcp" }]

      # command wires to serve(host, port) — the exact entrypoint is set when serve() is built (3b).
      # Left to the image's default entrypoint here; override at box-build time if needed.

      environment = [
        { name = "NEOS_ENV", value = var.environment },
        { name = "SYNAPSE_SERVER_NAME", value = var.synapse_server_name }, # puppet mxids: @neop_*:<server_name>
        { name = "NC_CHANNELS_PORT", value = tostring(var.nc_channels_port) },
        { name = "CONVEX_SITE_URL", value = var.convex_site_url },  # palace /mcp (in-process dispatch)
        { name = "CLASSIFIER_PROVIDER", value = var.llm_provider }, # in-process runtime LLM (D2/OpenRouter)
      ]

      # AS tokens (this file) + the runtime creds the in-process dispatch needs (from secrets.tf's set).
      secrets = concat(
        [for k in local.nc_channels_secret_keys : { name = k, valueFrom = aws_secretsmanager_secret.nc_channels[k].arn }],
        [
          { name = "OPENROUTER_API_KEY", valueFrom = aws_secretsmanager_secret.runtime["OPENROUTER_API_KEY"].arn },
          { name = "PALACE_BRIDGE_API_KEY", valueFrom = aws_secretsmanager_secret.runtime["PALACE_BRIDGE_API_KEY"].arn },
        ]
      )

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.nc_channels[0].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "nc-channels"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "nc_channels" {
  count           = var.enable_nc_channels ? 1 : 0
  name            = "${local.name}-nc-channels"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.nc_channels[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.nc_channels[0].id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.nc_channels[0].arn
  }
}
