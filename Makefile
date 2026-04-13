.PHONY: dev serve index score analyze digest refresh index-entireio index-local analyze-entireio refresh-entireio analyze-local refresh-local build-ui test lint fix fmt check init clean sync restart help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev: ## Run FastAPI (reload) + SvelteKit dev servers
	@echo "Starting backend on :8100..."
	@uv run uvicorn cinsights.main:app --reload --port 8100 &
	@cd ui && npm run dev

serve: ## Serve production build
	uv run cinsights serve

restart: build-ui ## Rebuild UI + restart server
	@kill $$(lsof -ti:8100) 2>/dev/null || true
	@sleep 1
	@uv run cinsights serve &
	@sleep 2
	@echo "Running at http://localhost:8100"

index: ## Index sessions (zero LLM cost, includes scoring)
	uv run cinsights index

score: ## Re-score existing sessions and show ranked results
	uv run cinsights score

analyze: ## LLM-analyze scored sessions (costs tokens)
	uv run cinsights analyze

digest: ## Generate global + per-project insights reports (last 30 days, concurrent)
	uv run cinsights digest --days 30

refresh: ## index → analyze → digest (the cron entrypoint)
	uv run cinsights refresh --hours 24 --days 30

index-entireio: ## Index Entireio checkpoints (set REPO=/path/to/repo)
	uv run cinsights index --source entireio --repo $(REPO) --hours 8760

index-local: ## Index local JSONL session files
	uv run cinsights index --source local --hours 8760

analyze-entireio: ## LLM-analyze Entireio sessions (set REPO=/path/to/repo)
	uv run cinsights analyze --source entireio --repo $(REPO)

refresh-entireio: ## Refresh from Entireio checkpoints (set REPO=/path/to/repo)
	uv run cinsights refresh --source entireio --repo $(REPO) --hours 8760 --days 30

analyze-local: ## LLM-analyze local sessions
	uv run cinsights analyze --source local

refresh-local: ## Refresh from local JSONL files
	uv run cinsights refresh --source local --hours 8760 --days 30

build-ui: ## Build SvelteKit to static files
	cd ui && npm run build

sync: ## Sync Python dependencies
	uv sync

test: ## Run all tests
	uv run pytest

test-cov: ## Run tests with coverage report
	uv run pytest --cov=cinsights --cov-report=term-missing

lint: ## Run linter (check only)
	uv run ruff check src/ tests/

fix: ## Auto-fix lint issues
	uv run ruff check --fix src/ tests/

fmt: ## Format code
	uv run ruff format src/ tests/

check: lint test ## Run lint + tests

init: ## First-time project setup
	uv sync
	cd ui && npm install
	@echo "\nReady. Run 'make dev' to start developing."

clean: ## Remove generated files
	rm -rf ui/build ui/.svelte-kit cinsights.db dist/ htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
