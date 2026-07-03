.PHONY: up down migrate test lint

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
