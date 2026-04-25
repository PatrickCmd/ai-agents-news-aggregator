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
