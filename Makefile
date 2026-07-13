.PHONY: up down migrate test lint worker api eval stack stack-down backup restore web web-dev

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

web:           ## Install web dependencies and build the SPA into web/dist
	cd web && npm install && npm run build

web-dev:       ## Run the SPA dev server (proxies /api and /health to :8000)
	cd web && npm run dev

eval:          ## Score retrieval and investigation quality against the golden set
	uv run argus eval retrieval && uv run argus eval investigation

stack:         ## Build and start postgres + api + worker (full app in containers)
	docker compose --profile app up -d --build --wait

stack-down:    ## Stop the app containers (postgres keeps running; volumes untouched)
	docker compose --profile app down api worker

backup:        ## pg_dump + raw-store tarball into backups/
	mkdir -p backups
	docker compose exec -T postgres pg_dump -U argus -Fc argus > backups/argus_$$(date +%Y%m%d_%H%M%S).dump
	tar czf backups/raw_$$(date +%Y%m%d_%H%M%S).tgz data/raw

restore:       ## Restore: make restore DB_DUMP=backups/x.dump RAW_TGZ=backups/y.tgz
	docker compose exec -T postgres pg_restore -U argus -d argus --clean --if-exists < $(DB_DUMP)
	tar xzf $(RAW_TGZ)
