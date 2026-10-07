# The Ticketmaster scraper runs as a Fargate task: EventBridge Scheduler starts it every
# 6 hours (scheduler.tf), it publishes to Redpanda and sends traces to Jaeger on the host
# over the VPC's private network, and archives raw pages to S3 with its own task role.
#
# The task definition itself is registered by deploy/deploy.sh on every deploy, from
# deploy/scraper-task.json, so its image always matches the commit on the host. The
# schedule names the family without a revision, which runs the latest one.

locals {
  scraper_family          = "concert-radar-scraper"
  scraper_task_family_arn = "arn:aws:ecs:${var.region}:${local.account_id}:task-definition/${local.scraper_family}"
  scraper_log_group       = "/ecs/${local.scraper_family}"
  ticketmaster_key_arn    = "arn:aws:ssm:${var.region}:${local.account_id}:parameter/concert-radar/ticketmaster_api_key"
  scraper_reachable_ports = { kafka = 19092, otlp = 4317 }
}

resource "aws_ecs_cluster" "main" {
  name = "concert-radar"
}

resource "aws_cloudwatch_log_group" "scraper" {
  name              = local.scraper_log_group
  retention_in_days = 14
}

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

# Used by ECS itself: pull the image, write logs, and inject the Ticketmaster key.
resource "aws_iam_role" "scraper_execution" {
  name               = "concert-radar-scraper-execution"
  description        = "ECS: start the scraper task (image pull, logs, Ticketmaster key)"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "scraper_execution" {
  role       = aws_iam_role.scraper_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "scraper_execution" {
  statement {
    sid       = "TicketmasterKey"
    actions   = ["ssm:GetParameters"]
    resources = [local.ticketmaster_key_arn]
  }
}

resource "aws_iam_role_policy" "scraper_execution" {
  name   = "concert-radar-scraper-execution"
  role   = aws_iam_role.scraper_execution.id
  policy = data.aws_iam_policy_document.scraper_execution.json
}

# Used by the scraper's own code: archive raw pages, nothing else.
resource "aws_iam_role" "scraper_task" {
  name               = "concert-radar-scraper-task"
  description        = "Scraper task: write raw Ticketmaster pages to S3"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "scraper_task" {
  statement {
    sid       = "RawPayloads"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.raw.arn}/raw/*"]
  }
}

resource "aws_iam_role_policy" "scraper_task" {
  name   = "concert-radar-scraper-task"
  role   = aws_iam_role.scraper_task.id
  policy = data.aws_iam_policy_document.scraper_task.json
}

# Outbound only: Ticketmaster and ECR over the internet, Redpanda and Jaeger on the host.
resource "aws_security_group" "scraper" {
  name        = "concert-radar-scraper"
  description = "Concert Radar scraper task: outbound only"
  vpc_id      = data.aws_vpc.default.id

  tags = {
    Name = "concert-radar-scraper"
  }
}

resource "aws_vpc_security_group_egress_rule" "scraper_all" {
  security_group_id = aws_security_group.scraper.id
  description       = "Ticketmaster, ECR, S3, and the host's Kafka and OTLP ports"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# The host accepts Kafka and OTLP only from the scraper's security group; the public
# internet still reaches nothing but 80 and 443.
resource "aws_vpc_security_group_ingress_rule" "host_from_scraper" {
  for_each = local.scraper_reachable_ports

  security_group_id            = aws_security_group.host.id
  description                  = "Scraper task to ${each.key} on the host"
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
  referenced_security_group_id = aws_security_group.scraper.id
}
