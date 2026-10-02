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
