#!/usr/bin/env bash
# scripts/scraper-deploy.sh — wrap services/scraper/deploy.py for CI + local use.
#
# Usage:   scripts/scraper-deploy.sh <env>
#   env: dev | test | prod
#
# Locally: AWS_PROFILE=aiengineer scripts/scraper-deploy.sh dev
# In CI: OIDC creds exported by aws-actions/configure-aws-credentials@v4.

set -euo pipefail

ENV="${1:?usage: $0 <env>  # dev | test | prod}"

case "$ENV" in
  dev|test|prod) ;;
  *)
    echo "error: env must be dev|test|prod (got: $ENV)" >&2
    exit 2
    ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "→ scraper-deploy: env=$ENV"
uv run python services/scraper/deploy.py --mode deploy --env "$ENV"
echo "✓ scraper-deploy: $ENV complete"
