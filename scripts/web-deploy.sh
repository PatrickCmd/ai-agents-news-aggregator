#!/usr/bin/env bash
# scripts/web-deploy.sh — build the Next.js static export, sync to S3, invalidate CloudFront.
#
# Usage:   scripts/web-deploy.sh <env>           # env = dev | test | prod
# Example: AWS_PROFILE=aiengineer scripts/web-deploy.sh dev
#
# Required env vars (CI gets these from GitHub Environment vars/secrets;
# locally export them yourself or `make web-deploy-local-dev` / -test / -prod
# pulls bucket/dist from terraform output for you):
#   S3_BUCKET                          — destination bucket name
#   CLOUDFRONT_DISTRIBUTION_ID         — distribution ID for invalidation
#   NEXT_PUBLIC_API_URL                — base URL of the backend (no /v1 suffix)
#   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY  — Clerk pk_test_/pk_live_ key for the env
#
# Optional:
#   AWS_PROFILE                        — local only; CI uses OIDC AssumeRole creds
#   SKIP_BUILD=1                       — sync existing web/out/ without rebuilding
#   SKIP_INVALIDATE=1                  — skip the CloudFront invalidation step

set -euo pipefail

ENV_NAME="${1:?usage: $0 <env>  # dev | test | prod}"

case "$ENV_NAME" in
  dev|test|prod) ;;
  *) echo "error: env must be dev|test|prod (got: $ENV_NAME)" >&2; exit 2 ;;
esac

: "${S3_BUCKET:?missing S3_BUCKET}"
: "${CLOUDFRONT_DISTRIBUTION_ID:?missing CLOUDFRONT_DISTRIBUTION_ID}"
: "${NEXT_PUBLIC_API_URL:?missing NEXT_PUBLIC_API_URL}"
: "${NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY:?missing NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "→ web-deploy: env=$ENV_NAME bucket=$S3_BUCKET dist=$CLOUDFRONT_DISTRIBUTION_ID"

# 1. Build (unless skipped)
if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  echo "→ Installing pnpm deps (--frozen-lockfile --ignore-scripts)"
  (cd web && pnpm install --frozen-lockfile --ignore-scripts)

  echo "→ Building static export"
  (cd web && \
    NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" \
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" \
    pnpm build)
else
  echo "→ Skipping build (SKIP_BUILD=1)"
fi

if [[ ! -d "web/out" ]]; then
  echo "error: web/out/ doesn't exist after build" >&2
  exit 3
fi

# 2. Sync to S3
echo "→ Syncing web/out/ → s3://$S3_BUCKET/"
aws s3 sync web/out/ "s3://$S3_BUCKET/" --delete

# 3. Invalidate CloudFront
if [[ "${SKIP_INVALIDATE:-0}" != "1" ]]; then
  echo "→ Creating CloudFront invalidation"
  INV_ID=$(aws cloudfront create-invalidation \
    --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
    --paths '/*' \
    --query 'Invalidation.Id' \
    --output text)
  echo "  invalidation: $INV_ID"
else
  echo "→ Skipping invalidation (SKIP_INVALIDATE=1)"
fi

echo "✓ web-deploy: $ENV_NAME complete"
