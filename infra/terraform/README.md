# AWS demo environment

One EC2 host in the default VPC runs the whole stack with Docker Compose.
GitHub Actions builds images, pushes them to ECR, and rolls out through SSM
Run Command. There is no SSH: port 22 is closed and the host has no key pair.

This configuration creates:

- an Amazon Linux 2023 `t3a.medium` host (30 GB encrypted gp3, 2 GB swap,
  IMDSv2 only) with an Elastic IP and a security group open on 80 and 443
- nine ECR repositories `concert-radar/*` (immutable tags, scan on push,
  last 10 images kept)
- the private bucket `concert-radar-raw-<account_id>` (`raw/` expires after 90 days)
- the host's instance role, the GitHub OIDC provider, and the deploy role
  that only `repo:hollywood-an/concert-radar:environment:production` can assume
- an EventBridge Scheduler schedule that runs the scraper on the host every 6 hours
- optionally, a 40 USD/month budget alert

## Before the first apply

1. Install Terraform 1.10 or newer and the AWS CLI, and sign in to the target
   account with credentials that can manage EC2, IAM, ECR, S3, SSM, Scheduler,
   and Budgets.
2. Store the Ticketmaster key under the default `aws/ssm` key (the host role
   has no KMS permissions, so a customer-managed key would not decrypt):

   ```sh
   read -rs TICKETMASTER_API_KEY
   aws ssm put-parameter --region us-east-2 --type SecureString \
     --name /concert-radar/ticketmaster_api_key --value "$TICKETMASTER_API_KEY"
   ```

3. If the account already has an OIDC provider for
   `token.actions.githubusercontent.com` (only one is allowed per account),
   pass `-var create_github_oidc_provider=false`. Its audiences must include
   `sts.amazonaws.com`.

## Apply

```sh
cd infra/terraform
terraform init
terraform plan -out tfplan -var budget_email=you@example.com
terraform apply tfplan
```

Leave `budget_email` out to skip the budget. State is local
(`terraform.tfstate`, gitignored). It holds no secrets but is the only record
of what was created, so keep a copy.

Put the outputs into GitHub as **repository** variables. They must be repository
variables, not `production` environment variables: the Deploy workflow's first job
checks `INSTANCE_ID` before any job enters the environment, and skips while it is empty.

| GitHub variable       | Terraform output  |
| --------------------- | ----------------- |
| `AWS_REGION`          | `region`          |
| `AWS_DEPLOY_ROLE_ARN` | `deploy_role_arn` |
| `ECR_REGISTRY`        | `ecr_registry`    |
| `INSTANCE_ID`         | `instance_id`     |
| `PUBLIC_HOST`         | `public_host`     |
| `RAW_BUCKET`          | `raw_bucket`      |

```sh
for pair in AWS_REGION=region AWS_DEPLOY_ROLE_ARN=deploy_role_arn \
  ECR_REGISTRY=ecr_registry INSTANCE_ID=instance_id \
  PUBLIC_HOST=public_host RAW_BUCKET=raw_bucket; do
  gh variable set "${pair%%=*}" --body "$(terraform output -raw "${pair#*=}")"
done
```

`PUBLIC_HOST` is the Elastic IP in sslip.io form (`3-14-15-92.sslip.io`), which
resolves to that IP without any DNS setup.

## On the host

- The first deploy generates `/concert-radar/jwt_secret`,
  `/concert-radar/postgres_password`, and `/concert-radar/jaeger_password` as
  SecureString parameters on the host. Terraform never creates or reads them,
  so they stay out of its state and outputs.
- First boot installs Docker, the Compose plugin, git, and the ECR credential
  helper, and creates `/opt/concert-radar` for the deploy checkout. Docker pulls
  from ECR with the instance role; there is no `docker login`.
- Open a shell with `aws ssm start-session --target <instance_id>` (needs the
  Session Manager plugin for the AWS CLI).
- The scraper runs every 6 hours as
  `/opt/concert-radar/deploy/compose.sh --profile jobs run --rm scraper`; each
  run shows up in `aws ssm list-commands --instance-id <instance_id>`.
- Later applies never replace the host: a newer AMI or an edited first-boot
  script is ignored. `terraform apply -replace=aws_instance.host` builds a fresh
  host, and the database on the old root volume is lost with it.

## Cost and teardown

About $1.12/day in us-east-2: the instance (~$0.90), the public IPv4 address
($0.12), the 30 GB volume (~$0.08), and a few cents of ECR and S3 storage.
CPU credits are `standard`, so the instance cannot run up surplus-credit charges.

Stopping the instance (`aws ec2 stop-instances --instance-ids <instance_id>`)
cuts the bill to about $0.20/day for the volume and the address. The Elastic IP
stays allocated, so the URL is the same after `start-instances`.

`terraform destroy` deletes everything above, including every image in ECR and
every object in the raw bucket. It leaves the four `/concert-radar/*` SSM
parameters, which were created outside Terraform; delete them by hand.
