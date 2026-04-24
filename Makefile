SHELL := /bin/bash
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

scraper-build: ## Build scraper Docker image locally
	docker build -f services/scraper/Dockerfile -t news-scraper:$(shell git rev-parse HEAD) \
	  --build-arg GIT_SHA=$(shell git rev-parse HEAD) .

scraper-deploy-build: ## Build + push scraper image to ECR
	uv run python services/scraper/deploy.py --mode build

scraper-deploy: ## Full scraper deploy via Terraform (requires #6 infra)
	uv run python services/scraper/deploy.py --mode deploy --env dev

scraper-serve: ## Run scraper FastAPI locally
	uv run python -m news_scraper serve

scraper-ingest: ## Run all pipelines locally and block until done
	uv run python -m news_scraper ingest --lookback-hours 24

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
