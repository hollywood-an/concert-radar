# Host instance role: SSM management, ECR pulls, the raw bucket, and the
# /concert-radar/* parameters.

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "host" {
  name               = "concert-radar-host"
  description        = "Concert Radar demo host"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "host_managed" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
  ])

  role       = aws_iam_role.host.name
  policy_arn = each.value
}

# The parameters are SecureStrings under the AWS-managed aws/ssm key, whose key
# policy already lets account principals use it through SSM, so no kms:*
# permission is needed here.
data "aws_iam_policy_document" "host" {
  statement {
    sid       = "RawPayloads"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.raw.arn}/raw/*"]
  }

  # AmazonSSMManagedInstanceCore already allows GetParameter(s) on every
  # parameter; this statement records what the app itself reads.
  statement {
    sid       = "ReadAppParameters"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:aws:ssm:${var.region}:${local.account_id}:parameter/concert-radar/*"]
  }

  # The first deploy generates these on the host, so Terraform never sees them.
  statement {
    sid     = "WriteGeneratedParameters"
    actions = ["ssm:PutParameter"]
    resources = [
      for name in ["jwt_secret", "postgres_password", "jaeger_password"] :
      "arn:aws:ssm:${var.region}:${local.account_id}:parameter/concert-radar/${name}"
    ]
  }
}

resource "aws_iam_role_policy" "host" {
  name   = "concert-radar-host"
  role   = aws_iam_role.host.id
  policy = data.aws_iam_policy_document.host.json
}

resource "aws_iam_instance_profile" "host" {
  name = "concert-radar-host"
  role = aws_iam_role.host.name
}

# GitHub Actions deploy role. GitHub reaches it in one of two ways (var.github_auth):
#
# - "access_key": an IAM user whose only permission is to assume this role. Its
#   access key lives in the repo's `production` environment secrets. This is the
#   default because the AWS Free plan's service control policy denies
#   iam:CreateOpenIDConnectProvider.
# - "oidc": GitHub's OIDC token, restricted to this repo's production
#   environment. Nothing long-lived is stored; use it wherever the account allows.

locals {
  github_oidc     = var.github_auth == "oidc"
  github_oidc_url = "https://token.actions.githubusercontent.com"
  github_oidc_provider_arn = (
    !local.github_oidc ? null :
    var.create_github_oidc_provider
    ? aws_iam_openid_connect_provider.github[0].arn
    : data.aws_iam_openid_connect_provider.github[0].arn
  )
}

# AWS trusts GitHub's OIDC signing certificate through its own CA store, so no
# thumbprint is pinned.
resource "aws_iam_openid_connect_provider" "github" {
  count = local.github_oidc && var.create_github_oidc_provider ? 1 : 0

  url            = local.github_oidc_url
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = local.github_oidc && !var.create_github_oidc_provider ? 1 : 0

  url = local.github_oidc_url
}

# The access key is created outside Terraform (see the README) so the secret
# never enters state. force_destroy lets `terraform destroy` remove the user
# together with that key.
resource "aws_iam_user" "deploy" {
  count = local.github_oidc ? 0 : 1

  name          = "concert-radar-github-deploy"
  force_destroy = true
}

data "aws_iam_policy_document" "deploy_user" {
  count = local.github_oidc ? 0 : 1

  # TagSession: the configure-aws-credentials action tags the role session.
  statement {
    sid       = "AssumeDeployRoleOnly"
    actions   = ["sts:AssumeRole", "sts:TagSession"]
    resources = [aws_iam_role.deploy.arn]
  }
}

resource "aws_iam_user_policy" "deploy" {
  count = local.github_oidc ? 0 : 1

  name   = "assume-deploy-role"
  user   = aws_iam_user.deploy[0].name
  policy = data.aws_iam_policy_document.deploy_user[0].json
}

data "aws_iam_policy_document" "github_assume" {
  dynamic "statement" {
    for_each = local.github_oidc ? [1] : []

    content {
      actions = ["sts:AssumeRoleWithWebIdentity"]

      principals {
        type        = "Federated"
        identifiers = [local.github_oidc_provider_arn]
      }

      condition {
        test     = "StringEquals"
        variable = "token.actions.githubusercontent.com:aud"
        values   = ["sts.amazonaws.com"]
      }

      condition {
        test     = "StringEquals"
        variable = "token.actions.githubusercontent.com:sub"
        values   = ["repo:${var.github_repo}:environment:production"]
      }
    }
  }

  dynamic "statement" {
    for_each = local.github_oidc ? [] : [1]

    content {
      actions = ["sts:AssumeRole", "sts:TagSession"]

      principals {
        type        = "AWS"
        identifiers = [aws_iam_user.deploy[0].arn]
      }
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "concert-radar-github-deploy"
  description        = "GitHub Actions production deploys for ${var.github_repo}"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # DescribeImages lets a re-run skip images already pushed for its commit,
  # since immutable tags reject a second push.
  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [for repo in aws_ecr_repository.app : repo.arn]
  }

  statement {
    sid     = "RunDeployOnHost"
    actions = ["ssm:SendCommand"]
    resources = [
      aws_instance.host.arn,
      local.run_shell_script_document_arn,
    ]
  }

  # These two actions do not support resource-level permissions.
  statement {
    sid = "ReadDeployResult"
    actions = [
      "ssm:GetCommandInvocation",
      "ssm:ListCommandInvocations",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "concert-radar-github-deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
