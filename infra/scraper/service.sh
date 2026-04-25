#!/usr/bin/env bash
#
# Helper for the ECS Express scraper service. Wraps common ops:
#
#   ./infra/scraper/service.sh redeploy   # force ECS to pull the latest image
#   ./infra/scraper/service.sh pause      # scale to 0 (stop paying for Fargate)
#   ./infra/scraper/service.sh resume     # scale to 1 (bring service up)
#   ./infra/scraper/service.sh pin-up     # suspend autoscaling and pin to 1 (dev sessions)
#   ./infra/scraper/service.sh pin-down   # re-enable autoscaling and scale back to 0
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

  pin-up)
    # Suspend autoscaling so the service stays at 1 task during dev sessions
    # without the autoscaler scaling it back to 0 after idle.
    echo "-> suspend autoscaling on $SERVICE"
    aws application-autoscaling register-scalable-target \
      --service-namespace ecs \
      --resource-id "service/$CLUSTER/$SERVICE" \
      --scalable-dimension ecs:service:DesiredCount \
      --suspended-state DynamicScalingInSuspended=true,DynamicScalingOutSuspended=true,ScheduledScalingSuspended=true \
      --profile "$PROFILE"

    echo "-> scale $SERVICE to 1 (pinned)"
    aws ecs update-service \
      --cluster "$CLUSTER" \
      --service "$SERVICE" \
      --desired-count 1 \
      --profile "$PROFILE" \
      --query 'service.{Desired:desiredCount,Status:status}' \
      --output table
    echo "   pinned at 1. Run 'pin-down' when you're done testing."
    ;;

  pin-down)
    # Re-enable autoscaling and scale back to 0.
    echo "-> resume autoscaling on $SERVICE"
    aws application-autoscaling register-scalable-target \
      --service-namespace ecs \
      --resource-id "service/$CLUSTER/$SERVICE" \
      --scalable-dimension ecs:service:DesiredCount \
      --suspended-state DynamicScalingInSuspended=false,DynamicScalingOutSuspended=false,ScheduledScalingSuspended=false \
      --profile "$PROFILE"

    echo "-> scale $SERVICE to 0"
    aws ecs update-service \
      --cluster "$CLUSTER" \
      --service "$SERVICE" \
      --desired-count 0 \
      --profile "$PROFILE" \
      --query 'service.{Desired:desiredCount,Status:status}' \
      --output table
    echo "   autoscaling re-enabled, scaled to 0 (back to cost-saving mode)."
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
    echo "-> autoscaling state"
    aws application-autoscaling describe-scalable-targets \
      --service-namespace ecs \
      --resource-ids "service/$CLUSTER/$SERVICE" \
      --profile "$PROFILE" \
      --query 'ScalableTargets[0].{Min:MinCapacity,Max:MaxCapacity,Suspended:SuspendedState}' \
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
    echo "usage: $0 {redeploy|pause|resume|pin-up|pin-down|status}" >&2
    exit 1
    ;;
esac
