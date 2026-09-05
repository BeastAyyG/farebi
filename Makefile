# Farebi — developer entry points.
# Run `make help` for the full list.

PYTHON      ?= .venv/Scripts/python
UV          ?= uv
PYTEST_ARGS ?=

.DEFAULT_GOAL := help
.PHONY: help install lock lint format type test test-all layers smoke clean serve ui docker-up docker-down

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the project with dev + face extras
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev,face]"

install-minimal: ## Install runtime + dev only (no MediaPipe); CI without face mesh
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

lock: ## Refresh uv.lock
	$(UV) lock --upgrade

format: ## Auto-fix formatting and safe lint issues
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

lint: ## Ruff + import-linter
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m importlinter.lint contracts

type: ## Static type check (mypy --strict)
	$(PYTHON) -m mypy

test: ## Fast test suite (skips tests marked slow)
	$(PYTHON) -m pytest -m "not slow" $(PYTEST_ARGS)

test-all: ## Full suite including slow tests
	$(PYTHON) -m pytest $(PYTEST_ARGS)

smoke: ## Run the end-to-end smoke test
	$(PYTHON) scripts/smoke_test.py

check: lint type test smoke ## Everything CI runs

serve: ## Start the API (Phase 08; not wired yet)
	$(PYTHON) -m uvicorn farebi.api.main:app --reload --port 8000

ui: ## Start the reviewer frontend (Phase 08b; not wired yet)
	cd frontend && npm run dev

docker-up: ## docker compose up --build
	docker compose up --build

docker-down:
	docker compose down

clean: ## Remove caches and build artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
