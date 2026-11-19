# AWS demo environment

One EC2 host in the default VPC runs the whole stack with Docker Compose.
GitHub Actions builds images, pushes them to ECR, and rolls out through SSM
Run Command. There is no SSH: port 22 is closed and the host has no key pair.

This configuration creates:

- an Amazon Linux 2023 `c7i-flex.large` host (2 vCPU, 4 GB; 30 GB encrypted gp3, 2 GB swap,
  IMDSv2 only) with an Elastic IP and a security group open on 80 and 443
- nine ECR repositories `concert-radar/*` (immutable tags, scan on push,
  last 10 images kept)
- the private bucket `concert-radar-raw-<account_id>` (`raw/` expires after 90 days)
- the host's instance role and the GitHub deploy role, plus one way for GitHub
  to assume that role (`github_auth`):
  - `access_key` (default): the IAM user `concert-radar-github-deploy`, which
    can do nothing but assume the deploy role
  - `oidc`: the GitHub OIDC provider, with the role assumable only by
    `repo:hollywood-an/concert-radar:environment:production`
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

3. Choose how GitHub signs in. The AWS Free plan's service control policy
   denies `iam:CreateOpenIDConnectProvider`, so the default is
   `github_auth=access_key`. On an account that allows OIDC providers, pass
   `-var github_auth=oidc` and nothing long-lived is stored. With OIDC, if the
   account already has a provider for `token.actions.githubusercontent.com`
   (only one is allowed per account), also pass
   `-var create_github_oidc_provider=false`; its audiences must include
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

### Deploy access key

Only with `github_auth=access_key`. Terraform creates the user but not its key,
so the secret never enters Terraform state. Create the key and hand it straight
to GitHub as `production` environment secrets; nothing is printed or written to
disk:

```sh
gh api -X PUT repos/{owner}/{repo}/environments/production --silent
aws iam create-access-key --user-name "$(terraform output -raw deploy_user)" \
  --query '[AccessKey.AccessKeyId,AccessKey.SecretAccessKey]' --output text |
  {
    read -r id secret
    gh secret set AWS_ACCESS_KEY_ID --env production --body "$id"
    gh secret set AWS_SECRET_ACCESS_KEY --env production --body "$secret"
  }
```

Environment secrets are readable only by jobs that run in the `production`
environment, and pull requests from forks never receive them. To rotate, run the
same commands again, then delete the old key (`aws iam list-access-keys` and
`aws iam delete-access-key`, both with `--user-name`). A user can hold two keys
at most. Deleting every key cuts GitHub off at once.

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

About $2.24/day in us-east-2: the instance (~$2.04), the public IPv4 address
($0.12), the 30 GB volume (~$0.08), and a few cents of ECR and S3 storage.

The default type is `c7i-flex.large` because an AWS **Free plan** account can
launch only a short list of instance types, and this is the cheapest one on it
with 4 GB of memory. On a Free plan the cost comes out of the plan's credits
($100 lasts about 45 days of uptime), nothing is ever charged to a card, and
`budget_email` can be left out. On a **Paid plan**, pass
`-var instance_type=t3a.medium` to cut the bill to about $1.12/day; T-family
hosts get `standard` CPU credits, so they cannot run up surplus-credit charges.

Before the first apply on a Free plan, confirm the account can launch the host:

```sh
# c7i-flex.large must be in this list
aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true \
  --query 'InstanceTypes[].InstanceType' --output text
# must print an image name, not []
aws ec2 describe-images --filters Name=free-tier-eligible,Values=true \
  --image-ids "$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text)" \
  --query 'Images[].Name'
# must be at least 2 (vCPUs for running On-Demand standard instances)
aws service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A \
  --query Quota.Value
```

Stopping the instance (`aws ec2 stop-instances --instance-ids <instance_id>`)
cuts the bill to about $0.20/day for the volume and the address. The Elastic IP
stays allocated, so the URL is the same after `start-instances`.

`terraform destroy` deletes everything above, including every image in ECR and
every object in the raw bucket. It leaves the four `/concert-radar/*` SSM
parameters, which were created outside Terraform; delete them by hand.
