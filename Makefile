.PHONY: up down reset test test-int lint types api

up:            ## infra (redpanda, neo4j); api/worker/frontend run on the host in dev
	docker compose up -d --wait

down:
	docker compose down

reset:         ## wipe volumes; topology is reseeded when the api starts
	docker compose down -v
	docker compose up -d --wait

test:          ## fast unit tests, no infra needed
	cd backend && uv run pytest -q

test-int:      ## needs `make up`
	cd backend && uv run pytest -q -m integration

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app scripts tests
	cd frontend && pnpm lint && pnpm typecheck

types:          ## export OpenAPI and regenerate frontend types
	cd backend && uv run python -m scripts.export_openapi
	cd frontend && pnpm types

api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000
