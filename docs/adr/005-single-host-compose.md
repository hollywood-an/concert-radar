# ADR 005: Deploy to one EC2 host with Docker Compose

## Status

Accepted. Replaces the spec's Kubernetes deployment with Kustomize overlays.

## Context

The demo needs to be live, cheap, and reproducible, and the deploy itself should show real
CI/CD practice. The stack is twelve containers (data stores, six services, web, Caddy,
Jaeger) that comfortably fit in 4 GB. Options considered:

- **EKS:** about $73/month for the control plane alone, plus nodes, before any traffic.
- **ECS Fargate:** per-task pricing for eleven long-running tasks, plus a load balancer
  (~$16/month), plus a managed or self-hosted broker; more moving parts than the app.
- **Kustomize manifests without a cluster:** nothing would exercise them, so they would prove
  little.
- **One EC2 instance running the same Compose stack as development:** about $34/month
  (t3a.medium, public IP, 30 GB disk), stoppable when idle.

## Decision

One t3a.medium (x86, matching the linux/amd64 images CI builds) runs `deploy/compose.prod.yml`. Terraform owns the host, its IAM role, ECR, S3, the
GitHub OIDC deploy role, and an EventBridge Scheduler that runs the scraper every six hours.
GitHub Actions builds images, pushes them to ECR tagged by commit, and rolls the host with SSM
Run Command; there is no SSH and no long-lived AWS key anywhere. Caddy terminates HTTPS with
Let's Encrypt certificates for `<ip>.sslip.io` hostnames, so no domain is needed.

## Consequences

- Production runs the same images and Compose topology as the local rehearsal
  (`deploy/compose.local.yml`), so most deploy problems surface on a laptop first.
- One host is a single point of failure, and a deploy restarts containers in place (seconds of
  downtime). Fine for a demo; the path to high availability is ECS services behind a load
  balancer with RDS and MSK, reusing the same images.
- The gateway's WebSocket push uses one Kafka consumer group, so it runs as a single replica;
  scaling it out would need per-replica groups or a fan-out layer.

## Update (2026-11-19)

The demo account is on the AWS Free plan, which can launch only a short list of instance
types, and t3a.medium is not on it. The default host is now a c7i-flex.large: the same
2 vCPU / 4 GB and x86 architecture, but about $2.24/day instead of $1.12/day, paid from the
plan's credits. `-var instance_type=t3a.medium` restores the original choice on a Paid plan.

The Free plan's service control policy also denies `iam:CreateOpenIDConnectProvider` (and SAML
providers and IAM Roles Anywhere), so GitHub cannot assume the deploy role through OIDC there.
The default is now `github_auth=access_key`: an IAM user whose only permission is to assume
the deploy role, with its access key in the repo's `production` environment secrets. This
gives up "no long-lived AWS key anywhere". The exposure is limited to what the deploy role can
do (push to nine ECR repositories and run commands on one host), the key is readable only by
jobs in the `production` environment, and it can be rotated or deleted at any time.
`-var github_auth=oidc` restores the keyless design on an account that allows it.
