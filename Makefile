# Single source of tasks. Recipes avoid shell-specific syntax so they run from
# PowerShell/cmd, Git Bash and CI alike.
.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help setup setup-ml lint format test smoke qdrant-up qdrant-down ingest index serve eval eval-gate

help: ## List available targets
	@$(UV) run --no-sync python scripts/make_help.py $(MAKEFILE_LIST)

setup: ## Create .venv (Python 3.12) and install dev deps + pre-commit hooks
	$(UV) sync
	$(UV) run pre-commit install

setup-ml: ## Install heavy local groups (CPU torch, embeddings, eval, demo)
	$(UV) sync --all-groups

lint: ## Ruff lint + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format: ## Apply ruff fixes and formatting
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

test: ## Unit tests (no network, no models)
	$(UV) run pytest

smoke: ## Networked smoke tests (needs .env keys)
	$(UV) run pytest -m smoke tests/smoke

qdrant-up: ## Start Qdrant in Docker
	docker compose up -d qdrant

qdrant-down: ## Stop Qdrant
	docker compose down

ingest: ## Parse the corpus into data/processed (phase 1)
	$(UV) run python -m aneel_rag.ingest

index: ## Chunk, embed and index into Qdrant (phase 2)
	$(UV) run python -m aneel_rag.retrieval.index

serve: ## Run the API (phase 6)
	$(UV) run uvicorn aneel_rag.api.app:app --reload

eval: ## Full local evaluation, writes eval/reports (phase 5)
	$(UV) run python eval/run_eval.py

eval-gate: ## Fail if metrics drop below eval/thresholds.yaml (phase 5)
	$(UV) run python eval/gate.py
