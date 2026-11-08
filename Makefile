.PHONY: help setup setup-backend setup-frontend \
        dev-backend dev-frontend \
        test test-backend test-frontend \
        lint build \
        docker-up docker-down docker-logs

# ── Default ──────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "RouteVision + Wayfinder — dev commands"
	@echo ""
	@echo "  Setup"
	@echo "    make setup            Install backend + frontend dependencies"
	@echo "    make setup-backend    Python venv + pip install"
	@echo "    make setup-frontend   npm install"
	@echo ""
	@echo "  Dev (run in separate terminals)"
	@echo "    make dev-backend      uvicorn on :8000 with --reload"
	@echo "    make dev-frontend     Vite dev server on :5173"
	@echo ""
	@echo "  Test"
	@echo "    make test             Run backend + frontend test suites"
	@echo "    make test-backend     pytest (91 tests)"
	@echo "    make test-frontend    node --test (geo + format helpers)"
	@echo ""
	@echo "  Lint / Build"
	@echo "    make lint             ruff check on backend"
	@echo "    make build            Vite production build"
	@echo ""
	@echo "  Docker"
	@echo "    make docker-up        docker compose up --build"
	@echo "    make docker-down      docker compose down"
	@echo "    make docker-logs      docker compose logs -f"
	@echo ""

# ── Setup ────────────────────────────────────────────────────────────────────
setup: setup-backend setup-frontend

setup-backend:
	cd backend && python3 -m venv .venv
	cd backend && .venv/bin/pip install --upgrade pip
	cd backend && .venv/bin/pip install -r requirements.txt
	@test -f backend/.env || (cp backend/.env.example backend/.env && echo "Created backend/.env from .env.example")

setup-frontend:
	cd frontend && npm install
	@test -f frontend/.env || (cp frontend/.env.example frontend/.env && echo "Created frontend/.env from .env.example")

# ── Dev ──────────────────────────────────────────────────────────────────────
dev-backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# ── Test ─────────────────────────────────────────────────────────────────────
test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/pytest -v

test-frontend:
	cd frontend && npm test

# ── Lint / Build ─────────────────────────────────────────────────────────────
lint:
	cd backend && .venv/bin/ruff check app tests

build:
	cd frontend && npm run build

# ── Docker ───────────────────────────────────────────────────────────────────
docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f
