sSHELL := /bin/bash
ALEMBIC := uv run alembic -c packages/db/alembic.ini
PYTEST := uv run pytest
MYPY := uv run mypy
RUFF := uv run ruff

.DEFAULT_GOAL := help

.PHONY: help install install-dev pre-commit-install \
        fmt lint typecheck check \
        test test-unit test-integration \
        test-scraper-unit test-scraper-live \
        scraper-build scraper-deploy-build scraper-deploy \
        scraper-serve scraper-ingest \
        scraper-redeploy scraper-pause scraper-resume scraper-status \
        scraper-pin-up scraper-pin-down scraper-recover \
        scraper-test-health scraper-test-ingest \
        scraper-test-ingest-rss scraper-test-ingest-youtube scraper-test-ingest-web \
        scraper-test-runs scraper-test-run \
        scraper-logs scraper-logs-follow \
        scraper-bootstrap scraper-import-secrets \
        scraper-destroy-service scraper-destroy \
        tf-bootstrap tf-scraper-init tf-scraper-plan tf-scraper-apply \
        secrets-sync \
        migrate migrate-down migrate-rev migration-history migration-current \
        seed reset-db \
        clean tag-foundation tag-ingestion

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---------- setup ----------

install: ## Sync all uv workspace packages + dev deps
	uv sync --all-packages

install-dev: install pre-commit-install ## Full developer setup

pre-commit-install: ## Install git hooks
	uv run pre-commit install

# ---------- quality ----------

fmt: ## Auto-format code with ruff
	$(RUFF) format .
	$(RUFF) check --fix .

lint: ## Lint + format check (no changes)
	$(RUFF) check .
	$(RUFF) format --check .

typecheck: ## Run mypy on packages/
	$(MYPY) packages

check: lint typecheck test ## lint + typecheck + tests (CI-equivalent)

pre-commit: ## Run all pre-commit hooks on every file
	uv run pre-commit run --all-files

# ---------- tests ----------

test: ## Run all tests (requires Docker for integration)
	$(PYTEST)

test-unit: ## Unit tests only (no Docker required)
	$(PYTEST) packages

test-integration: ## Integration tests only (Docker required)
	$(PYTEST) tests/integration

# ---------- scraper ----------

test-scraper-unit: ## Scraper unit tests (no Docker required)
	$(PYTEST) services/scraper/src/news_scraper/tests/unit -v

test-scraper-live: ## Scraper live smoke tests (hits real rss-mcp + YouTube)
	$(PYTEST) services/scraper/src/news_scraper/tests -m live -v

scraper-build: ## Build scraper Docker image locally (linux/amd64 for Fargate)
	docker build --platform=linux/amd64 -f services/scraper/Dockerfile \
	  -t news-scraper:$(shell git rev-parse HEAD) \
	  --build-arg GIT_SHA=$(shell git rev-parse HEAD) .

scraper-deploy-build: ## Build + push scraper image to ECR
	uv run python services/scraper/deploy.py --mode build

scraper-deploy: ## Full scraper deploy via Terraform (requires #6 infra)
	uv run python services/scraper/deploy.py --mode deploy --env dev

scraper-serve: ## Run scraper FastAPI locally
	uv run python -m news_scraper serve

scraper-ingest: ## Run all pipelines locally and block until done
	uv run python -m news_scraper ingest --lookback-hours 24

scraper-redeploy: ## Force ECS to pull the latest :latest tag (after make scraper-deploy-build)
	./infra/scraper/service.sh redeploy

scraper-pause: ## Scale ECS service to 0 (stop Fargate billing)
	./infra/scraper/service.sh pause

scraper-resume: ## Scale ECS service to 1 (bring it back up)
	./infra/scraper/service.sh resume

scraper-status: ## Show ECS service desired/running/pending + autoscaling + events
	./infra/scraper/service.sh status

scraper-pin-up: ## Pin service at 1 task (suspend autoscaling) for active testing
	./infra/scraper/service.sh pin-up

scraper-pin-down: ## Re-enable autoscaling + scale to 0 (cost-saving mode)
	./infra/scraper/service.sh pin-down

scraper-recover: ## Untaint service after a "Provider produced inconsistent result" error + reapply
	cd infra/scraper && terraform untaint aws_ecs_express_gateway_service.scraper && terraform apply -auto-approve

# ---------- scraper live endpoint testing ----------
# All targets read the endpoint from `terraform output -raw scraper_endpoint`.
# Override pipeline lookback windows with LOOKBACK=<hours>.

LOOKBACK ?= 6

scraper-test-health: ## curl /healthz on the live service
	@URL=https://$$(cd infra/scraper && terraform output -raw scraper_endpoint) && \
	  curl -s "$$URL/healthz" | jq

scraper-test-ingest: ## POST /ingest (all 3 pipelines)  [LOOKBACK=hrs]
	@URL=https://$$(cd infra/scraper && terraform output -raw scraper_endpoint) && \
	  curl -s -X POST "$$URL/ingest" \
	    -H 'content-type: application/json' \
	    -d '{"lookback_hours":$(LOOKBACK)}' | jq

scraper-test-ingest-rss: ## POST /ingest/rss  [LOOKBACK=hrs]
	@URL=https://$$(cd infra/scraper && terraform output -raw scraper_endpoint) && \
	  curl -s -X POST "$$URL/ingest/rss" \
	    -H 'content-type: application/json' \
	    -d '{"lookback_hours":$(LOOKBACK)}' | jq

scraper-test-ingest-youtube: ## POST /ingest/youtube  [LOOKBACK=hrs]
	@URL=https://$$(cd infra/scraper && terraform output -raw scraper_endpoint) && \
	  curl -s -X POST "$$URL/ingest/youtube" \
	    -H 'content-type: application/json' \
	    -d '{"lookback_hours":$(LOOKBACK)}' | jq

scraper-test-ingest-web: ## POST /ingest/web-search  [LOOKBACK=hrs]
	@URL=https://$$(cd infra/scraper && terraform output -raw scraper_endpoint) && \
	  curl -s -X POST "$$URL/ingest/web-search" \
	    -H 'content-type: application/json' \
	    -d '{"lookback_hours":$(LOOKBACK)}' | jq

scraper-test-runs: ## GET /runs (5 most recent)
	@URL=https://$$(cd infra/scraper && terraform output -raw scraper_endpoint) && \
	  curl -s "$$URL/runs?limit=5" | jq

scraper-test-run: ## GET /runs/$(RUN_ID) — requires RUN_ID=<uuid>
	@test -n "$(RUN_ID)" || (echo "RUN_ID required: make scraper-test-run RUN_ID=<uuid>" && exit 1)
	@URL=https://$$(cd infra/scraper && terraform output -raw scraper_endpoint) && \
	  curl -s "$$URL/runs/$(RUN_ID)" | jq

scraper-logs: ## Tail CloudWatch logs (last 5 min)  [SINCE=5m]
	aws logs tail /ecs/news-scraper --since $${SINCE:-5m} --profile aiengineer

scraper-logs-follow: ## Follow CloudWatch logs in real time
	aws logs tail /ecs/news-scraper --follow --profile aiengineer

# ---------- infra (terraform) ----------

tf-bootstrap: ## One-time Terraform state-backend bootstrap
	cd infra/bootstrap && terraform init && terraform apply

scraper-bootstrap: ## Fresh-start: provision scraper infra except the service (ECR/cluster/IAM/SSM/logs)
	cd infra/scraper && terraform apply \
	  -target=aws_ecr_repository.scraper \
	  -target=aws_ecr_lifecycle_policy.scraper \
	  -target=aws_ecs_cluster.main \
	  -target=aws_cloudwatch_log_group.scraper \
	  -target=aws_iam_role.task_execution \
	  -target=aws_iam_role_policy_attachment.task_execution_managed \
	  -target=aws_iam_role_policy.task_execution_ssm \
	  -target=aws_iam_role.infrastructure \
	  -target=aws_iam_role_policy_attachment.infrastructure_managed \
	  -target=aws_iam_role.task \
	  -target='aws_ssm_parameter.sensitive'
	@echo
	@echo "Next steps:"
	@echo "  make secrets-sync ENV=dev"
	@echo "  make scraper-deploy"

scraper-import-secrets: ## Import existing SSM params into state (fixes ParameterAlreadyExists)
	@cd infra/scraper && for key in \
	    supabase_db_url supabase_pooler_url openai_api_key \
	    langfuse_public_key langfuse_secret_key \
	    youtube_proxy_username youtube_proxy_password resend_api_key; do \
	  terraform import "aws_ssm_parameter.sensitive[\"$$key\"]" "/news-aggregator/$$(terraform workspace show)/$$key" || true; \
	done

scraper-destroy-service: ## Destroy only the ECS service (keeps cluster/ECR/IAM/SSM/logs)
	cd infra/scraper && terraform destroy \
	  -target=aws_ecs_express_gateway_service.scraper

scraper-destroy: ## DESTRUCTIVE: destroy ALL scraper AWS resources (ECS, ECR, IAM, SSM, logs)
	@read -p "This will delete every scraper resource in AWS. Type 'destroy' to confirm: " confirm \
	  && [ "$$confirm" = "destroy" ] || (echo "aborted" && exit 1)
	cd infra/scraper && terraform destroy

tf-scraper-init: ## Initialize scraper Terraform (requires STATE_BUCKET=...)
	@test -n "$(STATE_BUCKET)" || (echo "STATE_BUCKET required" && exit 1)
	cd infra/scraper && terraform init \
	  -backend-config="bucket=$(STATE_BUCKET)" \
	  -backend-config="key=scraper/terraform.tfstate" \
	  -backend-config="region=us-east-1" \
	  -backend-config="profile=aiengineer"

tf-scraper-plan: ## Show scraper Terraform plan
	cd infra/scraper && terraform plan

tf-scraper-apply: ## Apply scraper Terraform
	cd infra/scraper && terraform apply

secrets-sync: ## Push .env secrets into SSM (requires ENV=dev|prod)
	@test -n "$(ENV)" || (echo "ENV required: make secrets-sync ENV=dev" && exit 1)
	uv run python infra/scraper/sync_secrets.py --env $(ENV)

# ---------- database ----------

migrate: ## Apply all pending Alembic migrations
	$(ALEMBIC) upgrade head

migrate-down: ## Roll back one migration
	$(ALEMBIC) downgrade -1

migrate-rev: ## Create a new migration (usage: make migrate-rev MSG="add foo")
	@test -n "$(MSG)" || (echo "MSG required: make migrate-rev MSG='add foo'" && exit 1)
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

migration-history: ## Show migration history
	$(ALEMBIC) history

migration-current: ## Show current migration revision on the DB
	$(ALEMBIC) current

seed: ## Upsert dev user from config/user_profile.yml
	uv run python scripts/seed_user.py

reset-db: ## DESTRUCTIVE: drop + recreate public schema, re-migrate, re-seed (dev DB only)
	uv run python scripts/reset_db.py --confirm

# ---------- misc ----------

clean: ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

tag-foundation: ## Re-tag the Foundation release
	git tag -f -a foundation-v0.1.0 -m "Sub-project #0 Foundation"
	@echo "Push with: git push origin foundation-v0.1.0 --force"

tag-ingestion: ## Tag sub-project #1 ingestion
	git tag -f -a ingestion-v0.2.0 -m "Sub-project #1 Ingestion"
	@echo "Push with: git push origin ingestion-v0.2.0 --force"

# ---------- agents (#2) ----------

.PHONY: agents-digest agents-digest-sweep agents-editor agents-email agents-preview \
        digest-deploy-build digest-deploy digest-invoke \
        editor-deploy-build editor-deploy editor-invoke \
        email-deploy-build email-deploy email-invoke \
        agents-logs agents-logs-follow tag-agents

agents-digest:                ## summarise one article (ARTICLE_ID=...) — local CLI
	@test -n "$(ARTICLE_ID)" || (echo "ARTICLE_ID required" && exit 1)
	uv run python -m news_digest summarize $(ARTICLE_ID)

agents-digest-sweep:          ## summarise all unsummarised articles  [LOOKBACK=24]
	uv run python -m news_digest sweep --hours $${LOOKBACK:-24}

agents-editor:                ## rank for user (USER_ID=... LOOKBACK=24)
	@test -n "$(USER_ID)" || (echo "USER_ID required" && exit 1)
	uv run python -m news_editor rank $(USER_ID) --hours $${LOOKBACK:-24}

agents-email:                 ## send email for digest (DIGEST_ID=...)
	@test -n "$(DIGEST_ID)" || (echo "DIGEST_ID required" && exit 1)
	uv run python -m news_email send $(DIGEST_ID)

agents-preview:               ## preview email HTML (DIGEST_ID=...) → stdout
	@test -n "$(DIGEST_ID)" || (echo "DIGEST_ID required" && exit 1)
	uv run python -m news_email preview $(DIGEST_ID)

# ---- per-agent deploy ----

digest-deploy-build:          ## build + s3 upload (digest)
	uv run python services/agents/digest/deploy.py --mode build

digest-deploy:                ## build + terraform apply (digest)
	uv run python services/agents/digest/deploy.py --mode deploy --env dev

editor-deploy-build:          ## build + s3 upload (editor)
	uv run python services/agents/editor/deploy.py --mode build

editor-deploy:                ## build + terraform apply (editor)
	uv run python services/agents/editor/deploy.py --mode deploy --env dev

email-deploy-build:           ## build + s3 upload (email)
	uv run python services/agents/email/deploy.py --mode build

email-deploy:                 ## build + terraform apply (email) — requires MAIL_FROM
	@test -n "$(MAIL_FROM)" || (echo "MAIL_FROM required: MAIL_FROM=hi@yourdomain.com make email-deploy" && exit 1)
	uv run python services/agents/email/deploy.py --mode deploy --env dev

# ---- live invoke ----

digest-invoke:                ## aws lambda invoke (ARTICLE_ID=...)
	@test -n "$(ARTICLE_ID)" || (echo "ARTICLE_ID required" && exit 1)
	@aws lambda invoke --function-name news-digest-dev \
	  --payload '{"article_id":$(ARTICLE_ID)}' \
	  --cli-binary-format raw-in-base64-out \
	  /tmp/digest-out.json --profile aiengineer >/dev/null && jq . /tmp/digest-out.json

editor-invoke:                ## aws lambda invoke (USER_ID=...)
	@test -n "$(USER_ID)" || (echo "USER_ID required" && exit 1)
	@aws lambda invoke --function-name news-editor-dev \
	  --payload '{"user_id":"$(USER_ID)","lookback_hours":24}' \
	  --cli-binary-format raw-in-base64-out \
	  /tmp/editor-out.json --profile aiengineer >/dev/null && jq . /tmp/editor-out.json

email-invoke:                 ## aws lambda invoke (DIGEST_ID=...)
	@test -n "$(DIGEST_ID)" || (echo "DIGEST_ID required" && exit 1)
	@aws lambda invoke --function-name news-email-dev \
	  --payload '{"digest_id":$(DIGEST_ID)}' \
	  --cli-binary-format raw-in-base64-out \
	  /tmp/email-out.json --profile aiengineer >/dev/null && jq . /tmp/email-out.json

# ---- logs ----

agents-logs:                  ## tail one agent's logs (AGENT=digest|editor|email SINCE=10m)
	@test -n "$(AGENT)" || (echo "AGENT required: digest|editor|email" && exit 1)
	aws logs tail /aws/lambda/news-$(AGENT)-dev --since $${SINCE:-10m} --profile aiengineer

agents-logs-follow:           ## follow one agent's logs in real time (AGENT=digest|editor|email)
	@test -n "$(AGENT)" || (echo "AGENT required: digest|editor|email" && exit 1)
	aws logs tail /aws/lambda/news-$(AGENT)-dev --follow --profile aiengineer

# ---- tag ----

tag-agents:                   ## tag sub-project #2 release
	git tag -f -a agents-v0.3.0 -m "Sub-project #2 Agents (digest + editor + email Lambdas)"
	@echo "Push with: git push origin agents-v0.3.0"

# ---------- scheduler (#3) ----------

.PHONY: scheduler-deploy-build scheduler-deploy \
        scheduler-list-unsummarised scheduler-list-active-users scheduler-list-new-digests \
        cron-invoke cron-history cron-describe \
        remix-invoke remix-history \
        scheduler-logs scheduler-logs-follow tag-scheduler

scheduler-deploy-build:           ## build + s3 upload (scheduler)
	uv run python services/scheduler/deploy.py --mode build

scheduler-deploy:                 ## build + terraform apply (scheduler)
	uv run python services/scheduler/deploy.py --mode deploy --env dev

scheduler-list-unsummarised:      ## local CLI: print unsummarised article IDs  [LOOKBACK=24]
	uv run python -m news_scheduler list-unsummarised --hours $${LOOKBACK:-24}

scheduler-list-active-users:      ## local CLI: print active user IDs
	uv run python -m news_scheduler list-active-users

scheduler-list-new-digests:       ## local CLI: print today's GENERATED digest IDs
	uv run python -m news_scheduler list-new-digests

cron-invoke:                      ## start-execution on news-cron-pipeline-dev
	@CRON=$$(cd infra/scheduler && terraform output -raw cron_state_machine_arn) && \
	  aws stepfunctions start-execution --state-machine-arn "$$CRON" --input '{}' --profile aiengineer | jq

cron-history:                     ## list 5 most recent cron executions
	@CRON=$$(cd infra/scheduler && terraform output -raw cron_state_machine_arn) && \
	  aws stepfunctions list-executions --state-machine-arn "$$CRON" --max-items 5 --profile aiengineer \
	  --query 'executions[].{Status:status,Start:startDate,Name:name}' --output table

cron-describe:                    ## describe one execution by name (NAME=...)
	@test -n "$(NAME)" || (echo "NAME required: make cron-describe NAME=<exec-name>" && exit 1)
	@CRON=$$(cd infra/scheduler && terraform output -raw cron_state_machine_arn) && \
	  aws stepfunctions describe-execution \
	  --execution-arn "$${CRON/stateMachine/execution}:$(NAME)" \
	  --profile aiengineer | jq

remix-invoke:                     ## start-execution on news-remix-user-dev (USER_ID=...)
	@test -n "$(USER_ID)" || (echo "USER_ID required: make remix-invoke USER_ID=<uuid>" && exit 1)
	@REMIX=$$(cd infra/scheduler && terraform output -raw remix_state_machine_arn) && \
	  aws stepfunctions start-execution --state-machine-arn "$$REMIX" \
	  --input "{\"user_id\":\"$(USER_ID)\",\"lookback_hours\":$${LOOKBACK:-24}}" \
	  --profile aiengineer | jq

remix-history:                    ## list 5 most recent remix executions
	@REMIX=$$(cd infra/scheduler && terraform output -raw remix_state_machine_arn) && \
	  aws stepfunctions list-executions --state-machine-arn "$$REMIX" --max-items 5 --profile aiengineer \
	  --query 'executions[].{Status:status,Start:startDate,Name:name}' --output table

scheduler-logs:                   ## tail scheduler Lambda logs  [SINCE=10m]
	aws logs tail /aws/lambda/news-scheduler-dev --since $${SINCE:-10m} --profile aiengineer

scheduler-logs-follow:            ## follow scheduler Lambda logs in real time
	aws logs tail /aws/lambda/news-scheduler-dev --follow --profile aiengineer

tag-scheduler:                    ## tag sub-project #3
	git tag -f -a scheduler-v0.4.0 -m "Sub-project #3 Scheduler + Orchestration"
	@echo "Push with: git push origin scheduler-v0.4.0"

# ---------- api (#4) ----------

.PHONY: api-serve api-deploy-build api-deploy api-invoke api-test-me api-smoke \
        api-logs api-logs-follow tag-api

api-serve:                  ## run FastAPI locally on :8000
	uv run python -m news_api serve

api-deploy-build:           ## build + s3 upload (api)
	uv run python services/api/deploy.py --mode build

api-deploy:                 ## build + terraform apply (api)
	uv run python services/api/deploy.py --mode deploy --env dev

api-invoke:                 ## smoke /healthz on the deployed endpoint
	@URL=$$(cd infra/api && terraform output -raw api_endpoint) && \
	  curl -s "$$URL/v1/healthz" | jq

api-test-me:                ## test GET /me with $JWT (BYO token: export JWT=...)
	@test -n "$(JWT)" || (echo "JWT required: export JWT=<clerk-jwt>" && exit 1)
	@URL=$$(cd infra/api && terraform output -raw api_endpoint) && \
	  curl -s -H "Authorization: Bearer $(JWT)" "$$URL/v1/me" | jq

api-smoke:                  ## end-to-end smoke (requires USER_ID=user_xxx; see scripts/api-smoke.sh)
	@./scripts/api-smoke.sh

api-logs:                   ## tail api Lambda logs  [SINCE=10m]
	aws logs tail /aws/lambda/news-api-dev --since $${SINCE:-10m} --profile aiengineer

api-logs-follow:            ## follow api Lambda logs in real time
	aws logs tail /aws/lambda/news-api-dev --follow --profile aiengineer

tag-api:                    ## tag sub-project #4
	git tag -f -a api-v0.5.0 -m "Sub-project #4 API + Auth"
	@echo "Push with: git push origin api-v0.5.0"

# ---------- web (#5) ----------

.PHONY: web-install web-dev web-build web-test web-test-watch web-lint \
        web-typecheck web-osv \
        web-deploy-dev web-deploy-test web-deploy-prod \
        web-destroy-dev web-destroy-test web-destroy-prod \
        tag-web

web-install:                ## install pnpm deps (--ignore-scripts)
	cd web && pnpm install --frozen-lockfile --ignore-scripts

web-dev:                    ## run Next.js dev server (port 3000)
	cd web && pnpm dev

web-build:                  ## next build (static export → web/out/)
	cd web && pnpm build

web-test:                   ## vitest run (one-shot)
	cd web && pnpm test

web-test-watch:             ## vitest watch
	cd web && pnpm test:watch

web-lint:                   ## eslint check
	cd web && pnpm lint

web-typecheck:              ## tsc --noEmit
	cd web && pnpm typecheck

web-osv:                    ## OSV-Scanner against web/
	osv-scanner --recursive --fail-on-vuln web/

web-deploy-dev:             ## trigger web-deploy.yml for dev (gh CLI)
	gh workflow run web-deploy.yml -f environment=dev -f action=deploy

web-deploy-test:            ## trigger web-deploy.yml for test
	gh workflow run web-deploy.yml -f environment=test -f action=deploy

web-deploy-prod:            ## trigger web-deploy.yml for prod (requires reviewer)
	gh workflow run web-deploy.yml -f environment=prod -f action=deploy

web-destroy-dev:            ## DESTRUCTIVE: tear down dev infra
	@read -p "Type 'destroy-dev' to confirm: " c && [ "$$c" = "destroy-dev" ] || (echo aborted; exit 1)
	gh workflow run web-deploy.yml -f environment=dev -f action=destroy

web-destroy-test:           ## DESTRUCTIVE: tear down test infra
	@read -p "Type 'destroy-test' to confirm: " c && [ "$$c" = "destroy-test" ] || (echo aborted; exit 1)
	gh workflow run web-deploy.yml -f environment=test -f action=destroy

web-destroy-prod:           ## DESTRUCTIVE: tear down prod infra (use VERY carefully)
	@read -p "Type 'destroy-prod' to confirm: " c && [ "$$c" = "destroy-prod" ] || (echo aborted; exit 1)
	gh workflow run web-deploy.yml -f environment=prod -f action=destroy

tag-web:                    ## tag sub-project #5
	git tag -f -a frontend-v0.6.0 -m "Sub-project #5 Frontend (Next.js + Clerk + S3/CloudFront)"
	@echo "Push with: git push origin frontend-v0.6.0"
