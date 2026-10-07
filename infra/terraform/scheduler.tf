# Starts the scraper as a Fargate task every 6 hours (see ecs.tf); nothing on the host
# needs a cron entry.

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "concert-radar-scraper-schedule"
  description        = "EventBridge Scheduler: start the scraper task on Fargate"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  # The schedule names the family without a revision; RunTask authorizes the revision
  # it resolves to, so both forms are listed.
  statement {
    sid       = "RunScraperTask"
    actions   = ["ecs:RunTask"]
    resources = [local.scraper_task_family_arn, "${local.scraper_task_family_arn}:*"]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.main.arn]
    }
  }

  statement {
    sid       = "PassScraperRoles"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.scraper_execution.arn, aws_iam_role.scraper_task.arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "concert-radar-scraper-schedule"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "scraper" {
  name                = "concert-radar-scraper"
  description         = "Scrape Ticketmaster on Fargate"
  schedule_expression = "rate(6 hours)"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = local.scraper_task_family_arn
      launch_type         = "FARGATE"

      # A public IP in the default VPC's public subnet reaches ECR and Ticketmaster
      # without a NAT gateway; the security group admits no inbound traffic.
      network_configuration {
        subnets          = [local.host_subnet_id]
        security_groups  = [aws_security_group.scraper.id]
        assign_public_ip = true
      }
    }

    # Retries cover a failed RunTask call (for example, before the first deploy has
    # registered a task definition); the task's own exit code is in its ECS history.
    retry_policy {
      maximum_retry_attempts = 2
    }
  }
}
