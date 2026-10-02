# Runs the Ticketmaster scraper on the host every 6 hours through SSM Run
# Command; nothing on the host needs a cron entry.

locals {
  scraper_command = "/opt/concert-radar/deploy/compose.sh --profile jobs run --rm scraper"
}

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
  description        = "EventBridge Scheduler: start the scraper job on the demo host"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions = ["ssm:SendCommand"]
    resources = [
      aws_instance.host.arn,
      local.run_shell_script_document_arn,
    ]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "concert-radar-scraper-schedule"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "scraper" {
  name                = "concert-radar-scraper"
  description         = "Scrape Ticketmaster on the demo host"
  schedule_expression = "rate(6 hours)"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ssm:sendCommand"
    role_arn = aws_iam_role.scheduler.arn

    input = jsonencode({
      DocumentName = "AWS-RunShellScript"
      InstanceIds  = [aws_instance.host.id]
      Parameters = {
        commands = [local.scraper_command]
      }
    })

    # Retries cover a failed SendCommand call; the scraper's own exit status
    # is recorded in the SSM command history.
    retry_policy {
      maximum_retry_attempts = 2
    }
  }
}
