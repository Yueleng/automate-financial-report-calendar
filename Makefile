.PHONY: setup backend frontend test test-core test-backend test-frontend

setup:
	python3.12 -m venv backend/.venv || python3 -m venv backend/.venv
	backend/.venv/bin/pip install --upgrade pip
	backend/.venv/bin/pip install -r backend/requirements.txt
	cd frontend && pnpm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && pnpm dev

test-core:
	python3 -m unittest discover -s tests

test-backend:
	backend/.venv/bin/pytest backend/tests -q

test-frontend:
	cd frontend && pnpm lint && pnpm build

test: test-core test-backend test-frontend
