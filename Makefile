.PHONY: dev infra migrate seed test lint

infra:
	docker compose up -d

migrate:
	@for f in db/migrations/*.sql; do \
		echo "Running $$f..."; \
		psql $(DATABASE_URL_SYNC) -f $$f; \
	done

seed:
	psql $(DATABASE_URL_SYNC) -f db/seeds/genres.sql
	psql $(DATABASE_URL_SYNC) -f db/seeds/sample_venues.sql

dev-gateway:
	cd services/gateway && uv run uvicorn src.main:app --reload --port 8000

dev-scraper:
	cd services/scraper-ticketmaster && uv run python -m src.main

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
	$(MAKE) dev-enricher &
	$(MAKE) dev-matcher &
	$(MAKE) dev-notifier &
	$(MAKE) dev-web &
	wait

test:
	cd services/gateway && uv run pytest
	cd services/scraper-ticketmaster && uv run pytest
	cd services/enricher && uv run pytest
	cd services/matcher && uv run pytest
	cd services/notifier && uv run pytest
	cd web && pnpm test

lint:
	cd services/gateway && uv run ruff check . && uv run mypy .
	cd services/scraper-ticketmaster && uv run ruff check . && uv run mypy .
	cd web && pnpm lint
