# Production deploy

One EC2 host runs the whole stack with Docker Compose (`compose.prod.yml`); Caddy terminates
HTTPS for `<ip>.sslip.io` (web), `api.<ip>.sslip.io` (REST + WebSocket), and
`jaeger.<ip>.sslip.io` (traces, basic auth). The infrastructure is in
[`infra/terraform`](../infra/terraform).

## How a deploy happens

1. A commit lands on `main` and **CI** passes.
2. The **Deploy** workflow (`.github/workflows/deploy.yml`) assumes the deploy role, which can
   only push to the app's ECR repositories and run commands on the host. On the demo account
   it signs in with an IAM user's access key from the `production` environment secrets; that
   user can do nothing but assume the role. With `github_auth=oidc` it uses GitHub's OIDC token
   and no key is stored. It builds the 9 images for that commit
   (linux/amd64) and pushes them to ECR, tagged with the commit sha.
3. It sends `deploy.sh` to the host with **SSM Run Command** (no SSH; port 22 is closed). On
   the host, `deploy.sh`:
   - reads the Ticketmaster key from SSM Parameter Store, and generates the database password,
     JWT secret, and Jaeger password on the first deploy (stored back in SSM, reused after);
   - writes `/opt/concert-radar/.env.deploy` (mode 600);
   - pulls the images, applies new database migrations, creates Kafka topics, and runs
     `docker compose up -d --wait` until every service reports healthy.
   - on a database with no shows yet (the first deploy), runs one scrape, so the app has data
     without waiting six hours for the schedule.
4. A smoke job checks `https://api.<host>/readyz` and the home page.

**EventBridge Scheduler** runs the Ticketmaster scraper on the host every 6 hours
(`compose.sh --profile jobs run --rm scraper`); each raw API page is archived to S3.

## Setup (once, after `terraform apply`)

The workflow reads these **repository variables** (Settings → Secrets and variables → Actions →
Variables; none are secret), all from `terraform output`:

| Variable | `terraform output -raw ...` |
|---|---|
| `AWS_REGION` | `region` |
| `AWS_DEPLOY_ROLE_ARN` | `deploy_role_arn` |
| `ECR_REGISTRY` | `ecr_registry` |
| `INSTANCE_ID` | `instance_id` |
| `PUBLIC_HOST` | `public_host` |
| `RAW_BUCKET` | `raw_bucket` |

Until `INSTANCE_ID` is set, the Deploy workflow skips.

With the default `github_auth=access_key`, the workflow also reads two **`production`
environment secrets**, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. The
[Terraform README](../infra/terraform/README.md#deploy-access-key) has the commands that create
the key and store it without printing it.

## Frontend on Vercel (optional)

The same Next.js app can also be served from Vercel, calling the API on the EC2 host. The
host keeps serving its own copy, so either URL works.

1. Create a Vercel project from this repo with **Root Directory** `web`. Vercel detects
   Next.js and pnpm on its own.
2. Set the project environment variable `NEXT_PUBLIC_GATEWAY_URL` to `https://api.<PUBLIC_HOST>`
   for Production and Preview. It is inlined into the browser bundle at build time, so
   redeploy after changing it.
3. Let the API accept the Vercel origins: set the repository variable `CORS_ORIGIN_REGEX`
   and run the Deploy workflow. The pattern is matched against the whole origin, so list
   each allowed form, for example the production domain and the team's preview URLs:

   ```bash
   gh variable set CORS_ORIGIN_REGEX --body \
     'https://<project>\.vercel\.app|https://<project>-[a-z0-9-]+-<team-slug>\.vercel\.app'
   ```

Pushes to `main` then deploy to both places: Vercel builds the frontend, and the Deploy
workflow rolls the host. The WebSocket (`/ws/feed`) connects straight to the API host. If the
host's Elastic IP ever changes, update `NEXT_PUBLIC_GATEWAY_URL` and redeploy on Vercel.

## Operating it

```bash
# Roll back (or redeploy) a commit: images are immutable, so this only re-points the host.
gh workflow run Deploy -f sha=<commit sha>

# A shell on the host, without SSH (needs the Session Manager plugin for the AWS CLI).
aws ssm start-session --target <instance_id>
sudo /opt/concert-radar/deploy/compose.sh ps
sudo /opt/concert-radar/deploy/compose.sh logs -f --tail 100 enricher

# The Jaeger UI password (user: admin).
aws ssm get-parameter --with-decryption --name /concert-radar/jaeger_password \
  --query Parameter.Value --output text
```

## Rehearse locally

`compose.local.yml` builds every image locally and runs the same stack on a laptop, with
Caddy serving `https://localhost` and `https://api.localhost` from its own local CA:

```bash
cp deploy/local.env.example deploy/local.env
docker compose -f deploy/compose.prod.yml -f deploy/compose.local.yml \
  --env-file deploy/local.env up -d --build --wait
```
