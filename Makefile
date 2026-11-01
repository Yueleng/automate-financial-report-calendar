.PHONY: setup db-up db-down migrate seed backend frontend test test-backend test-frontend

setup:
	python3.12 -m venv backend/.venv || python3 -m venv backend/.venv
	backend/.venv/bin/pip install --upgrade pip
	backend/.venv/bin/pip install -r backend/requirements.txt
	cd frontend && pnpm install

db-up:
	docker compose up -d --wait db

db-down:
	docker compose down

migrate:
	cd backend && .venv/bin/alembic upgrade head

# One-off: import a legacy watchlist.csv, e.g. make seed CSV=watchlist.csv
seed:
	cd backend && .venv/bin/python -m app.seed --watchlist-csv $(abspath $(CSV))

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && pnpm dev

# Needs Postgres; set TEST_DATABASE_URL to a throwaway database (tables are truncated).
test-backend:
	backend/.venv/bin/pytest backend/tests -q

test-frontend:
	cd frontend && pnpm lint && pnpm build

test: test-backend test-frontend
