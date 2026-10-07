#!/usr/bin/env bash
# Roll the production stack to IMAGE_TAG. Runs on the EC2 host, as root, from a checkout
# of the commit being deployed (the Deploy workflow sends it over SSM Run Command):
#
#   IMAGE_TAG=<git sha> ECR_REGISTRY=<account>.dkr.ecr.<region>.amazonaws.com \
#   PUBLIC_HOST=<ip-with-dashes>.sslip.io AWS_REGION=us-east-2 RAW_BUCKET=<bucket> \
#   deploy/deploy.sh
#
# Secrets never pass through GitHub: the Ticketmaster key is read from SSM Parameter Store,
# and the database password, JWT secret, and Jaeger password are generated here on the
# first deploy and stored back in SSM, so every later deploy (or a rebuilt host) reuses them.
#
# It also registers the scraper's Fargate task definition (deploy/scraper-task.json) with
# the same image tag, so the scheduled scrape always runs the deployed code.
set -euo pipefail

: "${IMAGE_TAG:?}" "${ECR_REGISTRY:?}" "${PUBLIC_HOST:?}" "${AWS_REGION:?}"
cd "$(dirname "$0")/.."
ENV_FILE="${CONCERT_RADAR_ENV_FILE:-/opt/concert-radar/.env.deploy}"
CADDY_IMAGE=caddy:2.11.4-alpine

param() {
  aws ssm get-parameter --region "$AWS_REGION" --with-decryption \
    --name "/concert-radar/$1" --query Parameter.Value --output text
}

# Reuse the stored secret, or create it once. put-parameter without --overwrite refuses to
# replace an existing value, so a failed read can never rotate a live password.
generated() {
  local value
  if value=$(param "$1" 2>/dev/null); then
    printf '%s' "$value"
    return
  fi
  value=$(openssl rand -hex 32)
  aws ssm put-parameter --region "$AWS_REGION" --name "/concert-radar/$1" \
    --type SecureString --value "$value" >/dev/null
  echo "generated /concert-radar/$1" >&2
  printf '%s' "$value"
}

# The Fargate scraper reaches Redpanda and Jaeger at the host's private address (IMDSv2).
private_ip() {
  local token
  token=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
  curl -fsS -H "X-aws-ec2-metadata-token: $token" \
    http://169.254.169.254/latest/meta-data/local-ipv4
}
HOST_PRIVATE_IP=${HOST_PRIVATE_IP:-$(private_ip)}

ticketmaster_key=$(param ticketmaster_api_key) \
  || { echo "missing SSM parameter /concert-radar/ticketmaster_api_key" >&2; exit 1; }
postgres_password=$(generated postgres_password)
jwt_secret=$(generated jwt_secret)
jaeger_password=$(generated jaeger_password)
jaeger_hash=$(docker run --rm "$CADDY_IMAGE" caddy hash-password --plaintext "$jaeger_password")

umask 077
tmp=$(mktemp "$ENV_FILE.XXXXXX")
# Single quotes keep values literal when compose reads the file (the bcrypt hash has $s).
cat > "$tmp" <<EOF
IMAGE_TAG=$IMAGE_TAG
ECR_REGISTRY=$ECR_REGISTRY
PUBLIC_HOST=$PUBLIC_HOST
AWS_REGION=$AWS_REGION
RAW_BUCKET=${RAW_BUCKET:-}
HOST_PRIVATE_IP=$HOST_PRIVATE_IP
POSTGRES_PASSWORD=$postgres_password
JWT_SECRET=$jwt_secret
JAEGER_PASSWORD_HASH='$jaeger_hash'
TICKETMASTER_API_KEY='$ticketmaster_key'
EOF
mv "$tmp" "$ENV_FILE"

compose() { deploy/compose.sh "$@"; }

# The scraper image is pulled too, for the first-deploy scrape below.
compose --profile ops --profile jobs pull --quiet
# One-shot jobs run before `up --wait`, which can't treat exited containers as success.
compose --profile ops run --rm migrate
compose --profile ops run --rm topics
compose up -d --wait --wait-timeout 600 --remove-orphans
docker image prune -f >/dev/null

# Each deploy registers a new revision; the schedule runs the family's latest.
task_definition=$(mktemp)
ACCOUNT_ID=${ECR_REGISTRY%%.*} IMAGE_TAG=$IMAGE_TAG ECR_REGISTRY=$ECR_REGISTRY \
  AWS_REGION=$AWS_REGION RAW_BUCKET=${RAW_BUCKET:-} HOST_PRIVATE_IP=$HOST_PRIVATE_IP \
  python3 -c 'import os, string, sys; print(string.Template(sys.stdin.read()).substitute(os.environ))' \
  < deploy/scraper-task.json > "$task_definition"
revision=$(aws ecs register-task-definition --region "$AWS_REGION" \
  --cli-input-json "file://$task_definition" --query taskDefinition.revision --output text)
rm -f "$task_definition"
echo "registered task definition concert-radar-scraper:$revision"

# The schedule's first run fires while Terraform creates it, before anything is deployed,
# and the next is six hours out; a fresh database gets one scrape now instead. A failed
# scrape doesn't fail the deploy: the schedule retries it.
shows=$(compose exec -T postgres psql -U cr -d concertradar -tAc "SELECT count(*) FROM events")
if [ "$shows" = 0 ]; then
  echo "no shows yet; running the first scrape"
  compose --profile jobs run --rm scraper || echo "first scrape failed; the schedule will retry" >&2
fi

compose ps --format 'table {{.Service}}\t{{.Status}}'
echo "deployed $IMAGE_TAG to https://$PUBLIC_HOST"
