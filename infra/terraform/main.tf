data "aws_caller_identity" "current" {}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  ecr_registry = "${local.account_id}.dkr.ecr.${var.region}.amazonaws.com"

  run_shell_script_document_arn = "arn:aws:ssm:${var.region}::document/AWS-RunShellScript"

  # AL2023 does not package the Compose plugin, so the host installs this
  # release binary and checks it against the published checksum.
  compose_version = "v5.5.1"
  compose_sha256  = "db1889184726840f75c4f9c001048430d4f25b3be3cb084d3ddd762bc0aed576"
}

data "aws_vpc" "default" {
  default = true
}

data "aws_ec2_instance_type_offerings" "host" {
  location_type = "availability-zone"

  filter {
    name   = "instance-type"
    values = [var.instance_type]
  }

  lifecycle {
    postcondition {
      condition     = length(self.locations) > 0
      error_message = "${var.instance_type} is not offered in any availability zone of ${var.region}."
    }
  }
}

data "aws_subnets" "host" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "default-for-az"
    values = ["true"]
  }

  filter {
    name   = "availability-zone"
    values = data.aws_ec2_instance_type_offerings.host.locations
  }

  lifecycle {
    postcondition {
      condition     = length(self.ids) > 0
      error_message = "The default VPC has no default subnet in an availability zone that offers ${var.instance_type}."
    }
  }
}

data "aws_subnet" "host" {
  for_each = toset(data.aws_subnets.host.ids)
  id       = each.value
}

locals {
  # A different subnet would replace the host, so pick by AZ name (stable
  # across applies) rather than by subnet ID. values() orders by map key.
  subnet_id_by_az = { for s in data.aws_subnet.host : s.availability_zone => s.id }
  host_subnet_id  = values(local.subnet_id_by_az)[0]
}

resource "aws_security_group" "host" {
  name        = "concert-radar-host"
  description = "Concert Radar demo host: HTTP and HTTPS in, everything out. No SSH; use SSM."
  vpc_id      = data.aws_vpc.default.id

  tags = {
    Name = "concert-radar-host"
  }
}

resource "aws_vpc_security_group_ingress_rule" "web" {
  for_each = toset(["80", "443"])

  security_group_id = aws_security_group.host.id
  description       = "Public web traffic on port ${each.value}"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.host.id
  description       = "Package installs, ECR pulls, SSM, and outbound API calls"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  host_user_data = <<-EOT
    #!/bin/bash
    set -euxo pipefail

    # The Elastic IP replaces the launch-time public IP early in boot, which
    # can drop a download that is in flight.
    retry() {
      for _ in 1 2 3 4 5; do
        "$@" && return 0
        sleep 15
      done
      return 1
    }

    retry dnf install -y docker git amazon-ecr-credential-helper

    # 4 GB of RAM is tight for Postgres, Redpanda, six services, and Next.js.
    dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap defaults 0 0' >> /etc/fstab
    echo 'vm.swappiness=10' > /etc/sysctl.d/90-swappiness.conf
    sysctl --load /etc/sysctl.d/90-swappiness.conf

    install -d /usr/local/lib/docker/cli-plugins
    retry curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-compose \
      https://github.com/docker/compose/releases/download/${local.compose_version}/docker-compose-linux-x86_64
    echo '${local.compose_sha256}  /usr/local/lib/docker/cli-plugins/docker-compose' | sha256sum --check
    chmod 755 /usr/local/lib/docker/cli-plugins/docker-compose

    # Docker pulls from ECR with the instance role: no docker login, no stored token.
    install -d -m 700 /root/.docker
    echo '{"credHelpers": {"${local.ecr_registry}": "ecr-login"}}' > /root/.docker/config.json

    # json-file logs grow without bound by default and would fill the disk.
    install -d /etc/docker
    echo '{"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "3"}}' > /etc/docker/daemon.json

    systemctl enable --now docker
    install -d /opt/concert-radar
  EOT
}

resource "aws_instance" "host" {
  ami                    = data.aws_ssm_parameter.al2023_ami.insecure_value
  instance_type          = var.instance_type
  subnet_id              = local.host_subnet_id
  vpc_security_group_ids = [aws_security_group.host.id]
  iam_instance_profile   = aws_iam_instance_profile.host.name
  user_data              = local.host_user_data

  credit_specification {
    cpu_credits = "standard"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 30
    encrypted   = true
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
    # Containers sit one network hop behind the host; with the default limit
    # of 1 they could not reach IMDS for the instance role's credentials.
    http_put_response_hop_limit = 2
  }

  tags = {
    Name = "concert-radar"
  }

  lifecycle {
    # A newer AMI or an edited first-boot script must never replace the host.
    ignore_changes = [ami, user_data]
  }
}

resource "aws_eip" "host" {
  domain   = "vpc"
  instance = aws_instance.host.id

  tags = {
    Name = "concert-radar"
  }
}

resource "aws_budgets_budget" "monthly" {
  count = var.budget_email == "" ? 0 : 1

  name         = "concert-radar-monthly"
  budget_type  = "COST"
  limit_amount = "40"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }
}
