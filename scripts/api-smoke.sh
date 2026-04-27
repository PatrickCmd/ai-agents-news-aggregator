#!/usr/bin/env bash
#
# api-smoke.sh — end-to-end smoke test for the news-api Lambda.
#
# Hits /v1/healthz, /v1/me (×1), /v1/me/profile, /v1/digests, and /v1/remix
# with a Clerk JWT minted on the fly via the Backend API. Intended for use
# after `make api-deploy` to confirm:
#
#   - JWT verification works against the deployed CLERK_ISSUER
#   - Lazy upsert creates a row in `users` on the first authenticated call
#   - PUT /v1/me/profile flips profile_completed_at + writes an audit row
#   - POST /v1/remix starts a news-remix-user-dev Step Functions execution
#
# Prerequisites (one-time):
#
#   1. The API is deployed:
#        export CLERK_ISSUER=https://<your-clerk-frontend-api>
#        make api-deploy
#
#   2. A JWT template named `news-api` exists in the Clerk Dashboard.
#      Configure → JWT Templates → New template:
#        - Name:           news-api
#        - Token lifetime: 3600 (default 60s is too short for an interactive smoke)
#        - Claims JSON:
#            {
#              "email": "{{user.primary_email_address}}",
#              "name":  "{{user.full_name}}"
#            }
#      The API's ClerkClaims model requires `email` and `name`; the default
#      Clerk session token does NOT include them, hence the template.
#
#   3. CLERK_SECRET_KEY is reachable — either in the local shell, or stored
#      in SSM at /news-aggregator/${ENV}/clerk_secret_key (auto-loaded).
#
#   4. AWS profile `aiengineer` configured (override with AWS_PROFILE=...).
#
# Usage:
#   ./scripts/api-smoke.sh                               # lists Clerk users + exits
#   USER_ID=user_xxx ./scripts/api-smoke.sh              # full smoke (dev)
#   USER_ID=user_xxx SKIP_REMIX=1 ./scripts/api-smoke.sh # skip the SFN run
#   USER_ID=user_xxx ENV=prod ./scripts/api-smoke.sh     # prod env tree
#
# Exits non-zero on the first failure; output is `jq`-formatted for readability.

set -euo pipefail

ENV="${ENV:-dev}"
AWS_PROFILE="${AWS_PROFILE:-aiengineer}"
SKIP_REMIX="${SKIP_REMIX:-0}"
JWT_TEMPLATE="${JWT_TEMPLATE:-news-api}"
TF_DIR="${TF_DIR:-infra/api}"

if [[ -t 1 ]]; then
    BOLD="\033[1m"; CYAN="\033[36m"; GREEN="\033[32m"; YELLOW="\033[33m"; RESET="\033[0m"
else
    BOLD=""; CYAN=""; GREEN=""; YELLOW=""; RESET=""
fi

step() { printf "\n${BOLD}${CYAN}== %s ==${RESET}\n" "$*" >&2; }
note() { printf "${YELLOW}-> %s${RESET}\n" "$*" >&2; }
ok()   { printf "\n${GREEN}OK %s${RESET}\n" "$*" >&2; }
die()  { printf "${BOLD}ERROR: %s${RESET}\n" "$*" >&2; exit 1; }

# Sanity: required tools.
for tool in curl jq aws terraform; do
    command -v "$tool" >/dev/null || die "missing required tool: $tool"
done

# 1. Hydrate CLERK_SECRET_KEY from SSM if not already in env.
if [[ -z "${CLERK_SECRET_KEY:-}" ]]; then
    step "Reading CLERK_SECRET_KEY from SSM (/news-aggregator/${ENV}/clerk_secret_key)"
    CLERK_SECRET_KEY=$(aws ssm get-parameter \
        --name "/news-aggregator/${ENV}/clerk_secret_key" \
        --with-decryption \
        --profile "${AWS_PROFILE}" \
        --query Parameter.Value --output text 2>/dev/null) \
        || die "Could not read clerk_secret_key from SSM. Either seed it (see infra/README.md) or set CLERK_SECRET_KEY in your shell."
    export CLERK_SECRET_KEY
fi

# 2. If USER_ID isn't set, list Clerk users and exit cleanly.
if [[ -z "${USER_ID:-}" ]]; then
    step "Listing Clerk users (set USER_ID=user_xxx and re-run)"
    curl -s https://api.clerk.com/v1/users \
        -H "Authorization: Bearer ${CLERK_SECRET_KEY}" \
        | jq '.[] | {id, email: .email_addresses[0].email_address, name: ((.first_name // "") + " " + (.last_name // ""))}'
    exit 1
fi

# 3. Resolve the deployed API endpoint from Terraform output.
step "Reading api_endpoint from ${TF_DIR}"
URL=$(cd "${TF_DIR}" && terraform output -raw api_endpoint 2>/dev/null) \
    || die "Could not read api_endpoint from ${TF_DIR}. Has terraform been applied?"
note "URL: ${URL}"

# 4. Mint a fresh Clerk session for the user.
step "Creating Clerk session for ${USER_ID}"
SESSION_ID=$(curl -s -X POST https://api.clerk.com/v1/sessions \
    -H "Authorization: Bearer ${CLERK_SECRET_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"${USER_ID}\"}" | jq -r .id)
[[ "${SESSION_ID}" =~ ^sess_ ]] \
    || die "Session creation failed. Confirm USER_ID exists in Clerk and CLERK_SECRET_KEY is correct. Got: ${SESSION_ID}"
note "session_id: ${SESSION_ID}"

# 5. Mint a JWT via the news-api template (carries email + name + extended TTL).
step "Minting JWT via template '${JWT_TEMPLATE}'"
JWT=$(curl -s -X POST "https://api.clerk.com/v1/sessions/${SESSION_ID}/tokens/${JWT_TEMPLATE}" \
    -H "Authorization: Bearer ${CLERK_SECRET_KEY}" \
    -H "Content-Type: application/json" | jq -r .jwt)
[[ -n "${JWT}" && "${JWT}" != "null" ]] \
    || die "JWT mint failed. Confirm Clerk template '${JWT_TEMPLATE}' exists with email + name claims and a >120s lifetime."
note "JWT length: ${#JWT} chars"

# 6. Smoke /v1/healthz (no auth).
step "GET /v1/healthz (no auth)"
curl -s "${URL}/v1/healthz" | jq

# 7. GET /v1/me — exercises JWT verify + lazy upsert.
step "GET /v1/me (lazy-creates user row on first authenticated call)"
curl -s -H "Authorization: Bearer ${JWT}" "${URL}/v1/me" | jq

# 8. PUT /v1/me/profile — flips profile_completed_at + writes audit row.
step "PUT /v1/me/profile (flips profile_completed_at, writes audit log)"
curl -s -X PUT "${URL}/v1/me/profile" \
    -H "Authorization: Bearer ${JWT}" \
    -H "Content-Type: application/json" \
    -d '{
        "background": ["AI engineer"],
        "interests": {"primary":["LLMs","agents"],"secondary":["devops"],"specific_topics":["MCP servers"]},
        "preferences": {"content_type":["technical deep dives"],"avoid":["press releases"]},
        "goals": ["stay current on agent infra"],
        "reading_time": {"daily_limit":"20 minutes","preferred_article_count":"8"}
    }' | jq

# 9. GET /v1/digests — empty until a remix or cron run completes.
step "GET /v1/digests?limit=5 (empty until a digest is generated)"
curl -s -H "Authorization: Bearer ${JWT}" "${URL}/v1/digests?limit=5" | jq

# 10. POST /v1/remix — kicks off a news-remix-user-dev SFN execution.
if [[ "${SKIP_REMIX}" == "1" ]]; then
    step "Skipping POST /v1/remix (SKIP_REMIX=1)"
else
    step "POST /v1/remix (starts editor + email pipeline; ~30-60s end-to-end)"
    REMIX_RESPONSE=$(curl -s -X POST "${URL}/v1/remix" \
        -H "Authorization: Bearer ${JWT}" \
        -H "Content-Type: application/json" \
        -d '{"lookback_hours": 24}')
    echo "${REMIX_RESPONSE}" | jq
    EXEC_ARN=$(echo "${REMIX_RESPONSE}" | jq -r '.execution_arn // ""')
    if [[ -n "${EXEC_ARN}" ]]; then
        note "Track execution:"
        note "  aws stepfunctions describe-execution --execution-arn ${EXEC_ARN} --profile ${AWS_PROFILE} --query status"
    fi
fi

ok "smoke complete"
