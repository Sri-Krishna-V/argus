.PHONY: up down migrate test lint worker api eval

up:            ## Start Postgres (pgvector) and wait until healthy
	docker compose up -d --wait

down:          ## Stop Postgres
	docker compose down

migrate:       ## Apply database migrations
	uv run alembic upgrade head

test:          ## Run the test suite
	uv run pytest

lint:          ## Ruff + layered-architecture contract
	uv run ruff check src tests
	uv run lint-imports

worker:        ## Run the pipeline worker + connector scheduler
	uv run argus worker

api:           ## Run the API + UI
	uv run uvicorn argus.main:app --reload

eval:          ## Score retrieval and investigation quality against the golden set
	uv run argus eval retrieval && uv run argus eval investigation
