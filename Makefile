.PHONY: dev infra topics migrate seed test test-image lint

SERVICES := gateway scraper-ticketmaster deduper enricher matcher notifier

infra:
	docker compose up -d

topics:
	infra/redpanda/create-topics.sh

migrate:
	db/migrate.sh

seed:
	psql $(DATABASE_URL_SYNC) -f db/seeds/genres.sql
	psql $(DATABASE_URL_SYNC) -f db/seeds/sample_venues.sql

dev-gateway:
	cd services/gateway && uv run uvicorn src.main:app --reload --port 8000

dev-scraper:
	cd services/scraper-ticketmaster && uv run python -m src.main

dev-deduper:
	cd services/deduper && uv run python -m src.main

dev-enricher:
	cd services/enricher && uv run python -m src.main

dev-matcher:
	cd services/matcher && uv run python -m src.main

dev-notifier:
	cd services/notifier && uv run python -m src.main

dev-web:
	cd web && pnpm dev

dev: infra
	@echo "Starting all services..."
	$(MAKE) dev-gateway &
	$(MAKE) dev-deduper &
	$(MAKE) dev-enricher &
	$(MAKE) dev-matcher &
	$(MAKE) dev-notifier &
	$(MAKE) dev-web &
	wait

# Integration tests start this image through testcontainers.
test-image:
	docker build -t concert-radar-postgres:latest infra/postgres

test: test-image
	@for s in $(SERVICES); do (cd services/$$s && uv run pytest -q) || exit 1; done

lint:
	@for s in $(SERVICES); do \
		(cd services/$$s && uv run ruff check . && uv run ruff format --check . && uv run mypy .) || exit 1; \
	done
	cd web && pnpm exec tsc --noEmit && pnpm lint

.PHONY: bucket

# Creates the dev MinIO bucket the scraper archives raw Ticketmaster pages into.
bucket:
	docker compose exec -T minio mc alias set local http://localhost:9000 minioadmin minioadmin
	docker compose exec -T minio mc mb --ignore-existing local/concert-radar
