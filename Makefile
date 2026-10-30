.DEFAULT_GOAL := help

.PHONY: help env build up down logs ps migrate seed backend-test backend-lint frontend-test frontend-lint frontend-typecheck frontend-build worker-task

help:
	@echo "FlowTrack local development commands"
	@echo "  make env                Copy .env.example to .env (if absent)"
	@echo "  make build              Build Compose images"
	@echo "  make up                 Start all Compose services"
	@echo "  make migrate            Apply Alembic migrations as a controlled step"
	@echo "  make seed               Create idempotent development-only synthetic data"
	@echo "  make backend-test        Run backend pytest suite"
	@echo "  make frontend-test       Run frontend Vitest suite"

env:
	@test -f .env || cp .env.example .env

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

migrate:
	docker compose run --rm migrate

seed:
	docker compose run --rm api python -m app.db.seed

backend-test:
	docker compose run --rm api pytest

backend-lint:
	docker compose run --rm api ruff check . && docker compose run --rm api ruff format --check .

frontend-test:
	docker compose run --rm web npm run test -- --run

frontend-lint:
	docker compose run --rm web npm run lint

frontend-typecheck:
	docker compose run --rm web npm run typecheck

frontend-build:
	docker compose run --rm web npm run build

worker-task:
	docker compose exec -T worker celery -A app.tasks.celery_app:celery_app call flowtrack.diagnostic
