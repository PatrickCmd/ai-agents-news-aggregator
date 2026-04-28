#!/usr/bin/env bash
# scripts/lambda-deploy.sh — wrap services/<x>/deploy.py for CI + local use.
#
# Usage:   scripts/lambda-deploy.sh <service> <env>
#   service: digest | editor | email | scheduler | api
#   env:     dev | test | prod
#
# Locally: AWS_PROFILE=aiengineer scripts/lambda-deploy.sh digest dev
# In CI: aws-actions/configure-aws-credentials@v4 exports OIDC creds before this runs.

set -euo pipefail

SVC="${1:?usage: $0 <service> <env>}"
ENV="${2:?usage: $0 <service> <env>}"

case "$SVC" in
  digest|editor|email)
    DEPLOY_PY="services/agents/$SVC/deploy.py"
    ;;
  scheduler|api)
    DEPLOY_PY="services/$SVC/deploy.py"
    ;;
  *)
    echo "error: unknown service '$SVC' (must be digest|editor|email|scheduler|api)" >&2
    exit 2
    ;;
esac

case "$ENV" in
  dev|test|prod) ;;
  *)
    echo "error: env must be dev|test|prod (got: $ENV)" >&2
    exit 2
    ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "→ lambda-deploy: service=$SVC env=$ENV"
uv run python "$DEPLOY_PY" --mode deploy --env "$ENV"
echo "✓ lambda-deploy: $SVC@$ENV complete"
