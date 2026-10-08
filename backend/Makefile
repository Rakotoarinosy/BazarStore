# Utilise uv s'il est installé, sinon un virtualenv .venv géré avec pip.
ifneq ($(shell command -v uv 2>/dev/null),)
    RUN := uv run
    INSTALL := uv sync --extra dev
else
    RUN := .venv/bin/python -m
    INSTALL := python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
endif

COMPOSE := docker compose
PORT ?= 8000

.PHONY: help install dev test lint format migrate seed revision requirements docker-up docker-down clean

help: ## Liste les commandes
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  make %-14s %s\n", $$1, $$2}'

install: ## Installe les dépendances (+ crée .env depuis .env.example)
	$(INSTALL)
	@test -f .env || (cp .env.example .env && echo ".env créé depuis .env.example")

dev: ## Lance l'API avec rechargement automatique
	$(RUN) uvicorn src.main:app --reload --port $(PORT)

test: ## Lance tous les tests
	$(RUN) pytest

lint: ## Vérifie le code : ruff + black --check + mypy
	$(RUN) ruff check src tests alembic
	$(RUN) black --check src tests alembic/env.py
	$(RUN) mypy src tests alembic/env.py

format: ## Corrige et formate le code : ruff --fix + black
	$(RUN) ruff check --fix src tests alembic
	$(RUN) black src tests alembic/env.py

migrate: ## Applique les migrations (alembic upgrade head)
	$(RUN) alembic upgrade head

seed: ## Remplit la base locale avec des données fictives (rejouable)
	$(RUN) python -m src.infrastructure.persistence.seed

revision: ## Génère une migration : make revision m="add products table"
	@test -n "$(m)" || (echo 'Usage : make revision m="description"' && exit 1)
	$(RUN) alembic revision --autogenerate -m "$(m)"

requirements: ## Régénère requirements.txt (prod, Passenger) et requirements-dev.txt depuis uv.lock
	uv lock
	uv export --frozen --no-emit-project --no-hashes -o requirements.txt
	uv export --frozen --no-emit-project --no-hashes --extra dev -o requirements-dev.txt

docker-up: ## Démarre les conteneurs
	$(COMPOSE) up --build

docker-down: ## Arrête les conteneurs
	$(COMPOSE) down

clean: ## Supprime caches, *.pyc et la base SQLite locale
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} +
	find . -type f -name "*.pyc" -not -path "./.venv/*" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -f app.db
