#!/usr/bin/env bash
#
# One-time IAM setup for the aiengineer user.
#
# AWS caps managed-policy attachments at 10 per group by default, so we split
# the project's policy bundle across two groups:
#
#   NewsAggregatorCoreAccess    — services used today (scraper / #1)
#   NewsAggregatorComputeAccess — services added in #2-#5
#
# Must be run with an admin-capable profile (default: patrickcmd).
#
# Usage:
#   ./infra/setup-iam.sh                    # ADMIN_PROFILE=patrickcmd
#   ADMIN_PROFILE=admin ./infra/setup-iam.sh
#
# Idempotent: re-running silently skips anything that already exists. Other
# errors (bad credentials, missing user, typo'd policy ARN) still crash.

set -euo pipefail

USER_NAME="${USER_NAME:-aiengineer}"
ADMIN_PROFILE="${ADMIN_PROFILE:-patrickcmd}"

CORE_GROUP="NewsAggregatorCoreAccess"
CORE_POLICIES=(
  "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess"
  "arn:aws:iam::aws:policy/AmazonECS_FullAccess"
  "arn:aws:iam::aws:policy/AmazonSSMFullAccess"
  "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
  "arn:aws:iam::aws:policy/IAMFullAccess"
  "arn:aws:iam::aws:policy/AWSCertificateManagerFullAccess"
  "arn:aws:iam::aws:policy/AmazonRoute53FullAccess"
  "arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess"
  "arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess"
)

COMPUTE_GROUP="NewsAggregatorComputeAccess"
COMPUTE_POLICIES=(
  "arn:aws:iam::aws:policy/AWSLambda_FullAccess"
  "arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator"
  "arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess"
  "arn:aws:iam::aws:policy/AmazonS3FullAccess"
  "arn:aws:iam::aws:policy/CloudFrontFullAccess"
)

echo "== IAM setup =="
echo "  admin profile: $ADMIN_PROFILE"
echo "  user:          $USER_NAME"
echo "  core group:    $CORE_GROUP    (${#CORE_POLICIES[@]} policies)"
echo "  compute group: $COMPUTE_GROUP (${#COMPUTE_POLICIES[@]} policies)"
echo

# Verify admin profile is usable.
echo "-> sts:GetCallerIdentity via $ADMIN_PROFILE"
aws sts get-caller-identity --profile "$ADMIN_PROFILE" --output table

# AWS SDK error code for "already exists" on IAM ops:
#   - CreateGroup, CreateUser       -> EntityAlreadyExists
#   - AddUserToGroup                -> idempotent (no error when already a member)
#   - AttachGroupPolicy             -> idempotent (no error when already attached)
# So we swallow EntityAlreadyExists only.

run_idempotent() {
  # run_idempotent <cmd...>  -- crashes on any error except EntityAlreadyExists
  local err
  if err=$("$@" 2>&1 >/dev/null); then
    return 0
  fi
  if echo "$err" | grep -q 'EntityAlreadyExists\|already exists'; then
    return 0
  fi
  echo "ERROR: $*" >&2
  echo "$err" >&2
  exit 1
}

ensure_group() {
  local group="$1"
  shift
  local -a policies=("$@")

  echo
  echo "-> ensure group: $group"
  run_idempotent aws iam create-group --group-name "$group" --profile "$ADMIN_PROFILE"
  echo "   group OK."

  echo "   attaching ${#policies[@]} policies:"
  for arn in "${policies[@]}"; do
    aws iam attach-group-policy \
      --group-name "$group" \
      --policy-arn "$arn" \
      --profile "$ADMIN_PROFILE"
    echo "     OK: $arn"
  done

  echo "   add $USER_NAME -> $group"
  aws iam add-user-to-group \
    --user-name "$USER_NAME" \
    --group-name "$group" \
    --profile "$ADMIN_PROFILE"
  echo "   done."
}

ensure_group "$CORE_GROUP"    "${CORE_POLICIES[@]}"
ensure_group "$COMPUTE_GROUP" "${COMPUTE_POLICIES[@]}"

echo
echo "-> groups for $USER_NAME:"
aws iam list-groups-for-user \
  --user-name "$USER_NAME" \
  --profile "$ADMIN_PROFILE" \
  --query 'Groups[].GroupName' \
  --output table

for g in "$CORE_GROUP" "$COMPUTE_GROUP"; do
  echo
  echo "-> policies on $g:"
  aws iam list-attached-group-policies \
    --group-name "$g" \
    --profile "$ADMIN_PROFILE" \
    --query 'AttachedPolicies[].PolicyName' \
    --output table
done

echo
echo "Done. Retry 'terraform apply' with the aiengineer profile."
