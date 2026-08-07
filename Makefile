.PHONY: help install install-dev test test-unit test-integration test-coverage lint lint-fix format run dev-build docker-build docker-up docker-down migrate migrate-create clean

help:
	@echo "Context Memory - Available Commands:"
	@echo "  install           Install production dependencies"
	@echo "  install-dev       Install development dependencies"
	@echo "  test              Run all tests"
	@echo "  test-unit         Run unit tests"
	@echo "  test-integration  Run integration tests"
	@echo "  test-coverage     Run tests with coverage report"
	@echo "  lint              Run all linters (ruff, mypy, bandit)"
	@echo "  lint-fix          Auto-fix linting issues"
	@echo "  format            Format code with ruff"
	@echo "  run               Start development server"
	@echo "  docker-build      Build Docker image"
	@echo "  docker-up         Start all services with Docker Compose"
	@echo "  docker-down       Stop all Docker Compose services"
	@echo "  migrate           Run Alembic migrations"
	@echo "  migrate-create    Create new Alembic migration"
	@echo "  clean             Remove build artifacts and cache files"

install:
	pip install --upgrade pip
	pip install -e .

install-dev:
	pip install --upgrade pip
	pip install -e .[dev]

test:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit/ -v --tb=short -m unit

test-integration:
	pytest tests/integration/ -v --tb=short -m integration

test-coverage:
	pytest --cov=src/context_memory --cov-report=html --cov-report=xml --cov-report=term-missing

lint:
	ruff check src/ tests/
	mypy src/ --strict
	bandit -r src/ -c pyproject.toml

lint-fix:
	ruff check --fix src/ tests/

format:
	ruff format src/ tests/

run:
	uvicorn context_memory.main:app --host 0.0.0.0 --port 8000 --reload --log-level info

docker-build:
	docker build -t context-memory:latest .

docker-up:
	docker-compose up -d --build

docker-down:
	docker-compose down -v

migrate:
	alembic upgrade head

migrate-create:
	@read -p "Enter migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/ htmlcov/ dist/ build/
