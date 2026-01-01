.PHONY: install test lint clean run help

help:
	@echo "Available commands:"
	@echo "  make install  - Install dependencies using uv"
	@echo "  make test     - Run tests with pytest"
	@echo "  make lint     - Run linting with ruff"
	@echo "  make run      - Run the agent CLI (interactive)"
	@echo "  make clean    - Remove build artifacts and cache"

install:
	uv sync

test:
	uv run pytest tests

lint:
	uv run ruff check src tests

run:
	uv run python -m src.main

api:
	uv run uvicorn src.server:app --reload --port 8000

clean:
	rm -rf .venv
	rm -rf .pytest_cache
	rm -rf src/__pycache__
	rm -rf tests/__pycache__
	rm -rf data/*.duckdb
	find . -type d -name "__pycache__" -exec rm -rf {} +
