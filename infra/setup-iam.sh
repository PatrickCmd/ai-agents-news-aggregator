#!/usr/bin/env bash
#
# One-time IAM setup: create NewsAggregatorAccess group, attach
# service-specific AWS-managed FullAccess policies for every service the
# project touches, and add the aiengineer user to it.
#
# Must be run with an admin-capable profile (default: patrickcmd).
#
# Usage:
#   ./infra/setup-iam.sh                    # ADMIN_PROFILE=patrickcmd
#   ADMIN_PROFILE=admin ./infra/setup-iam.sh
#
# Idempotent: safe to re-run.

set -euo pipefail

GROUP_NAME="${GROUP_NAME:-NewsAggregatorAccess}"
USER_NAME="${USER_NAME:-aiengineer}"
ADMIN_PROFILE="${ADMIN_PROFILE:-patrickcmd}"

# Service-specific managed policies covering every AWS service this project
# touches across sub-projects #1-#5. Tighten later if you want least-privilege
# per-service inline policies.
POLICIES=(
  # --- Scraper (#1) + ECS Express ---
  "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess"  # ECR
  "arn:aws:iam::aws:policy/AmazonECS_FullAccess"                  # ECS clusters/services
  "arn:aws:iam::aws:policy/AmazonSSMFullAccess"                   # SSM Parameter Store
  "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"              # CloudWatch Logs
  "arn:aws:iam::aws:policy/IAMFullAccess"                         # create roles + pass-role
  "arn:aws:iam::aws:policy/AWSCertificateManagerFullAccess"       # ACM certs
  "arn:aws:iam::aws:policy/AmazonRoute53FullAccess"               # Route53 records
  "arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess"        # ALB/TG ops (ECS Express)
  "arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess"               # VPC/subnet/SG describes
  # (Application Auto-Scaling for ECS is already covered by AmazonECS_FullAccess)
  # --- Future sub-projects ---
  "arn:aws:iam::aws:policy/AWSLambda_FullAccess"                  # #2 agents, #4 API Lambda
  "arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator"         # #4 API Gateway
  "arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess"           # #3 scheduler
  "arn:aws:iam::aws:policy/AmazonS3FullAccess"                    # tf state + #5 frontend
  "arn:aws:iam::aws:policy/CloudFrontFullAccess"                  # #5 frontend
)

echo "== IAM setup =="
echo "  admin profile: $ADMIN_PROFILE"
echo "  group:         $GROUP_NAME"
echo "  user to add:   $USER_NAME"
echo "  policies:      ${#POLICIES[@]}"
echo

# 1. Verify admin profile
echo "-> sts:GetCallerIdentity via $ADMIN_PROFILE"
aws sts get-caller-identity --profile "$ADMIN_PROFILE" --output table

# 2. Create group (ignore AlreadyExists)
echo
echo "-> create-group $GROUP_NAME"
if aws iam create-group --group-name "$GROUP_NAME" --profile "$ADMIN_PROFILE" 2>/dev/null; then
  echo "   created."
else
  echo "   already exists (OK)."
fi

# 3. Attach managed policies (idempotent)
echo
echo "-> attach managed policies"
for arn in "${POLICIES[@]}"; do
  if aws iam attach-group-policy \
      --group-name "$GROUP_NAME" \
      --policy-arn "$arn" \
      --profile "$ADMIN_PROFILE" 2>/dev/null; then
    echo "   attached: $arn"
  else
    echo "   FAILED:   $arn (policy may not exist — verify name)" >&2
  fi
done

# 4. Add user to group
echo
echo "-> add-user-to-group $USER_NAME -> $GROUP_NAME"
aws iam add-user-to-group \
  --user-name "$USER_NAME" \
  --group-name "$GROUP_NAME" \
  --profile "$ADMIN_PROFILE"
echo "   done."

# 5. Verify
echo
echo "-> current policies on $GROUP_NAME:"
aws iam list-attached-group-policies \
  --group-name "$GROUP_NAME" \
  --profile "$ADMIN_PROFILE" \
  --query 'AttachedPolicies[].PolicyName' \
  --output table

echo
echo "-> groups for $USER_NAME:"
aws iam list-groups-for-user \
  --user-name "$USER_NAME" \
  --profile "$ADMIN_PROFILE" \
  --query 'Groups[].GroupName' \
  --output table

echo
echo "Done. Retry 'terraform apply' with the aiengineer profile."
