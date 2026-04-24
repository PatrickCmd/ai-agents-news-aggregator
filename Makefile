SHELL := /bin/bash
ALEMBIC := uv run alembic -c packages/db/alembic.ini
PYTEST := uv run pytest
MYPY := uv run mypy
RUFF := uv run ruff

.DEFAULT_GOAL := help

.PHONY: help install install-dev pre-commit-install \
        fmt lint typecheck check \
        test test-unit test-integration \
        migrate migrate-down migrate-rev migration-history migration-current \
        seed reset-db \
        clean tag-foundation

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
