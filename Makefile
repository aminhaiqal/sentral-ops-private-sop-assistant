PYTHON ?= python3.12
BACKEND_PYTHON = backend/.venv/bin/python

.PHONY: setup check lint test build format

setup:
	$(PYTHON) -m venv backend/.venv
	$(BACKEND_PYTHON) -m pip install -r backend/requirements-dev.txt
	npm --prefix frontend ci

check: lint test build

lint:
	$(BACKEND_PYTHON) -m ruff check backend
	$(BACKEND_PYTHON) -m ruff format --check backend
	npm --prefix frontend run format:check

test:
	cd backend && .venv/bin/python -m pytest
	npm --prefix frontend test

build:
	npm --prefix frontend run build

format:
	$(BACKEND_PYTHON) -m ruff check --fix backend
	$(BACKEND_PYTHON) -m ruff format backend
	npm --prefix frontend run format
