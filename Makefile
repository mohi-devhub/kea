.PHONY: up down reset test test-int scenarios fixtures demo-check lint types api worker

up:            ## full stack (redpanda, neo4j, api, worker, frontend)
	docker compose up -d --wait redpanda neo4j
	docker compose up redpanda-init
	docker compose up -d --build --wait api worker frontend

down:
	docker compose down

reset:         ## wipe volumes; topology is reseeded when the api starts
	docker compose down -v
	docker compose up -d --wait redpanda neo4j
	docker compose up redpanda-init

test:          ## fast unit tests, no infra needed
	cd backend && uv run pytest -q

test-int:      ## needs `make up`
	cd backend && uv run pytest -q -m integration

demo-check:    ## M2 live-stack smoke checks
	cd backend && uv run pytest -q -m integration

scenarios:     ## batch-mode S1-S4 tuning-seed acceptance matrix
	cd backend && uv run python -m scripts.run_scenarios

fixtures:      ## create deterministic frontend replay fixtures from batch mode
	cd backend && uv run python -m scripts.gen_fixtures

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app scripts tests
	cd frontend && pnpm lint && pnpm typecheck

types:          ## export OpenAPI and regenerate frontend types
	cd backend && uv run python -m scripts.export_openapi
	cd frontend && pnpm types

api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

worker:
	cd backend && uv run python -m app.stream.worker
