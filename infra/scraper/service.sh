#!/usr/bin/env bash
#
# Helper for the ECS Express scraper service. Wraps three common ops:
#
#   ./infra/scraper/service.sh redeploy   # force ECS to pull the latest image
#   ./infra/scraper/service.sh pause      # scale to 0 (stop paying for Fargate)
#   ./infra/scraper/service.sh resume     # scale to 1 (bring service up)
#   ./infra/scraper/service.sh status     # show desired/running/pending + recent events
#
# All commands use AWS_PROFILE=aiengineer by default.

set -euo pipefail

PROFILE="${AWS_PROFILE:-aiengineer}"
CLUSTER="${ECS_CLUSTER:-news-aggregator}"
ENV_NAME="${ENV:-dev}"
SERVICE="scraper-${ENV_NAME}"

cmd="${1:-status}"

case "$cmd" in
  redeploy)
    echo "-> force-new-deployment on $SERVICE"
    aws ecs update-service \
      --cluster "$CLUSTER" \
      --service "$SERVICE" \
      --force-new-deployment \
      --profile "$PROFILE" \
      --query 'service.deployments[0].{rolloutState:rolloutState,desiredCount:desiredCount}' \
      --output table
    echo
    echo "-> waiting for service to stabilize (up to 10 min)..."
    aws ecs wait services-stable \
      --cluster "$CLUSTER" \
      --services "$SERVICE" \
      --profile "$PROFILE"
    echo "   stable."
    ;;

  pause)
    echo "-> scaling $SERVICE down to 0"
    aws ecs update-service \
      --cluster "$CLUSTER" \
      --service "$SERVICE" \
      --desired-count 0 \
      --profile "$PROFILE" \
      --query 'service.{Desired:desiredCount,Status:status}' \
      --output table
    echo "   paused (Fargate billing stops once tasks drain)."
    ;;

  resume)
    echo "-> scaling $SERVICE up to 1"
    aws ecs update-service \
      --cluster "$CLUSTER" \
      --service "$SERVICE" \
      --desired-count 1 \
      --profile "$PROFILE" \
      --query 'service.{Desired:desiredCount,Status:status}' \
      --output table
    echo "   scaling up. New task ready in ~60-90s."
    ;;

  status)
    echo "-> $SERVICE counts"
    aws ecs describe-services \
      --cluster "$CLUSTER" \
      --services "$SERVICE" \
      --profile "$PROFILE" \
      --query 'services[0].{Desired:desiredCount,Running:runningCount,Pending:pendingCount,Status:status}' \
      --output table
    echo
    echo "-> recent events"
    aws ecs describe-services \
      --cluster "$CLUSTER" \
      --services "$SERVICE" \
      --profile "$PROFILE" \
      --query 'services[0].events[:5].[createdAt,message]' \
      --output table
    ;;

  *)
    echo "usage: $0 {redeploy|pause|resume|status}" >&2
    exit 1
    ;;
esac
