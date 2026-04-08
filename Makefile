.PHONY: dev serve analyze digest build-ui test lint fix fmt check init clean sync restart help

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

analyze: ## Run analysis on recent sessions (last 24h)
	uv run cinsights analyze

digest: ## Generate global insights report (last 30 days)
	uv run cinsights digest --days 30

digest-all: ## Generate global + all per-project digests
	uv run cinsights digest --days 30
	@for proj in $$(uv run python -c "from cinsights.db.engine import get_engine; from cinsights.db.models import CodingSession; from sqlmodel import Session, select, func; e=get_engine(); s=Session(e); [print(r[0]) for r in s.exec(select(CodingSession.project_name).where(CodingSession.project_name.isnot(None)).group_by(CodingSession.project_name)).all()]"); do \
		echo "Generating digest for $$proj..."; \
		uv run cinsights digest --project "$$proj" --days 30; \
	done

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
	uv run cinsights init-db
	@echo "\nReady. Run 'make dev' to start developing."

clean: ## Remove generated files
	rm -rf ui/build ui/.svelte-kit cinsights.db dist/ htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
