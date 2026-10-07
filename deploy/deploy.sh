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
POSTGRES_PASSWORD=$postgres_password
JWT_SECRET=$jwt_secret
JAEGER_PASSWORD_HASH='$jaeger_hash'
TICKETMASTER_API_KEY='$ticketmaster_key'
EOF
mv "$tmp" "$ENV_FILE"

compose() { deploy/compose.sh "$@"; }

# The scraper image is pulled now too, so the scheduled run never waits on a pull.
compose --profile ops --profile jobs pull --quiet
# One-shot jobs run before `up --wait`, which can't treat exited containers as success.
compose --profile ops run --rm migrate
compose --profile ops run --rm topics
compose up -d --wait --wait-timeout 600 --remove-orphans
docker image prune -f >/dev/null
compose ps --format 'table {{.Service}}\t{{.Status}}'
echo "deployed $IMAGE_TAG to https://$PUBLIC_HOST"
