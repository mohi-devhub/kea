.PHONY: up down reset test test-int scenarios eval fixtures demo-check lint types api worker

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

test-int:      ## needs redpanda+neo4j; stops api/worker/frontend (they would steal the test's consumer group and /reset wipes shared Neo4j)
	docker compose stop api worker frontend
	cd backend && uv run pytest -q -m integration

demo-check:    ## end-to-end smoke of S1-S4 through the running stack (`make up` first)
	cd backend && uv run python -m scripts.demo_check

scenarios:     ## batch-mode S1-S4 tuning-seed acceptance matrix
	cd backend && uv run python -m scripts.run_scenarios

eval:          ## held-out benchmark report (template fallback if no LLM key is configured)
	cd backend && uv run python -m app.eval run

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
