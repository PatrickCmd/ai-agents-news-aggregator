#!/usr/bin/env bash
# Destroy Terraform-managed infra modules locally with full access.
#
# The CI OIDC roles (gh-actions-deploy-*) are deliberately too narrow to run
# `terraform destroy` — teardown always runs locally via AWS_PROFILE.
#
# Usage:
#   scripts/infra-destroy.sh [--env dev|test|prod] [--profile aiengineer] [--yes] <service ...|all>
#
# Design: docs/superpowers/specs/2026-08-12-infra-destroy-script-design.md
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../infra" && pwd)"

# Reverse-dependency order: api reads scheduler's outputs via
# terraform_remote_state, so api goes first; every module's alarms read the
# alerts SSM parameter, so alerts goes last.
ALL_ORDER=(api scheduler email editor digest scraper web alerts)

ENV=dev
PROFILE=aiengineer
ASSUME_YES=0
SERVICES=()

usage() {
  cat <<EOF
Usage: $(basename "$0") [--env dev|test|prod] [--profile <aws-profile>] [--yes] <service ...|all>

Services: ${ALL_ORDER[*]}
  all        destroy every service, in order: ${ALL_ORDER[*]}

Options:
  --env      Terraform workspace to destroy (default: dev)
  --profile  AWS profile with full access (default: aiengineer)
  --yes      skip the typed confirmation prompt
EOF
}

err() { echo "error: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --env)     ENV="${2:?--env needs a value}"; shift 2 ;;
    --profile) PROFILE="${2:?--profile needs a value}"; shift 2 ;;
    --yes)     ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*)        usage >&2; err "unknown option: $1" ;;
    *)         SERVICES+=("$1"); shift ;;
  esac
done

case "$ENV" in dev|test|prod) ;; *) err "--env must be dev, test, or prod (got: $ENV)" ;; esac
[ ${#SERVICES[@]} -gt 0 ] || { usage >&2; err "no service given"; }

# Expand/validate the service list.
TARGETS=()
for s in "${SERVICES[@]}"; do
  if [ "$s" = "all" ]; then
    TARGETS=("${ALL_ORDER[@]}")
    break
  elif [ "$s" = "bootstrap" ]; then
    err "refusing to destroy 'bootstrap' — it holds the Terraform state bucket + lock
       table for every other module. Tear it down manually (local state) only after
       everything else is gone: cd infra/bootstrap && terraform destroy"
  elif [[ " ${ALL_ORDER[*]} " == *" $s "* ]]; then
    TARGETS+=("$s")
  else
    err "unknown service: $s (valid: ${ALL_ORDER[*]} | all)"
  fi
done

# Dummy values for required vars — irrelevant on destroy, they only satisfy
# validation (see infra/README.md "Required vars must be set").
module_vars() {
  case "$1" in
    api)       echo "-var=zip_s3_key=anything -var=zip_sha256=anything -var=clerk_issuer=https://placeholder.example.com" ;;
    digest|editor) echo "-var=zip_s3_key=anything -var=zip_sha256=anything" ;;
    email)     echo "-var=zip_s3_key=anything -var=zip_sha256=anything -var=mail_from=placeholder@example.com" ;;
    scheduler) echo "-var=zip_s3_key=anything -var=zip_sha256=anything -var=scraper_base_url=https://placeholder.example.com" ;;
    web)
      case "$ENV" in
        prod) echo "-var=subdomain=digest.patrickcmd.dev" ;;
        *)    echo "-var=subdomain=${ENV}-digest.patrickcmd.dev" ;;
      esac ;;
    *)         echo "" ;;
  esac
}

if [ "$ASSUME_YES" -ne 1 ]; then
  echo "About to DESTROY env '$ENV' of: ${TARGETS[*]}"
  expected="destroy-$ENV"; [ "$ENV" = "prod" ] && expected="destroy-prod-really"
  read -r -p "Type '$expected' to confirm: " answer
  [ "$answer" = "$expected" ] || { echo "aborted"; exit 1; }
fi

export AWS_PROFILE="$PROFILE"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
STATE_BUCKET="news-aggregator-tf-state-${ACCOUNT_ID}"

# Purge every object version + delete marker so a versioned bucket can be deleted.
empty_bucket() {
  local bucket="$1" batch n
  echo ">>> emptying versioned bucket: $bucket"
  while : ; do
    batch=$(aws s3api list-object-versions --bucket "$bucket" --max-items 500 --output json \
      --query '{Objects: [Versions[].{Key:Key,VersionId:VersionId}, DeleteMarkers[].{Key:Key,VersionId:VersionId}][] | [0:500]}')
    n=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["Objects"] or []))' <<<"$batch")
    [ "$n" = "0" ] && break
    aws s3api delete-objects --bucket "$bucket" --delete "$batch" \
      --query 'length(Deleted)' --output text
  done
}

destroy_module() {
  local mod="$1" vars log
  local dir="$INFRA_DIR/$mod"
  [ -d "$dir" ] || err "no such module directory: $dir"

  echo ""
  echo "=== [$mod] init + select workspace '$ENV' ==="
  # -upgrade: several modules' committed lock files predate the aws-provider
  # ~>6.42 constraint bump; init would otherwise fail on the mismatch.
  terraform -chdir="$dir" init -reconfigure -upgrade -input=false \
    -backend-config="bucket=$STATE_BUCKET" \
    -backend-config="key=$mod/terraform.tfstate" \
    -backend-config="region=us-east-1"

  if ! terraform -chdir="$dir" workspace list | grep -qx "[* ]* *$ENV"; then
    echo "=== [$mod] no '$ENV' workspace — nothing deployed, skipping ==="
    return 0
  fi
  terraform -chdir="$dir" workspace select "$ENV"

  # shellcheck disable=SC2086 — vars is a flat list of -var=k=v tokens
  vars=$(module_vars "$mod")
  log=$(mktemp)
  echo "=== [$mod] terraform destroy ==="
  if ! terraform -chdir="$dir" destroy -auto-approve -input=false $vars 2>&1 | tee "$log"; then
    # Versioned buckets can't be deleted while they hold object versions.
    local bucket
    bucket=$(sed -n 's/.*deleting S3 Bucket (\([^)]*\)).*BucketNotEmpty.*/\1/p' "$log" | head -1)
    [ -n "$bucket" ] || { rm -f "$log"; err "[$mod] destroy failed (see output above)"; }
    empty_bucket "$bucket"
    echo "=== [$mod] retrying terraform destroy ==="
    terraform -chdir="$dir" destroy -auto-approve -input=false $vars
  fi
  rm -f "$log"
}

for mod in "${TARGETS[@]}"; do
  destroy_module "$mod"
done

echo ""
echo "Done. Destroyed env '$ENV' of: ${TARGETS[*]}"
