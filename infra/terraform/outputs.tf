output "instance_id" {
  description = "Demo host instance ID (GitHub variable INSTANCE_ID)."
  value       = aws_instance.host.id
}

output "public_ip" {
  description = "Elastic IP of the demo host."
  value       = aws_eip.host.public_ip
}

output "public_host" {
  description = "sslip.io hostname that resolves to the Elastic IP (GitHub variable PUBLIC_HOST)."
  value       = "${replace(aws_eip.host.public_ip, ".", "-")}.sslip.io"
}

output "ecr_registry" {
  description = "ECR registry host (GitHub variable ECR_REGISTRY)."
  value       = local.ecr_registry
}

output "deploy_role_arn" {
  description = "Role GitHub Actions assumes through OIDC (GitHub variable AWS_DEPLOY_ROLE_ARN)."
  value       = aws_iam_role.deploy.arn
}

output "raw_bucket" {
  description = "Private bucket for raw scraper payloads (GitHub variable RAW_BUCKET)."
  value       = aws_s3_bucket.raw.bucket
}

output "region" {
  description = "AWS region (GitHub variable AWS_REGION)."
  value       = var.region
}
