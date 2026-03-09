# HL Data Loading & Cleaning — dev targets
.PHONY: test lint ci

test:
	python -m pytest tests/ -v

lint:
	ruff check .
	ruff format --check .

lint-fix:
	ruff check . --fix
	ruff format .

ci: lint test
