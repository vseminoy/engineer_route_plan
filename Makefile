# Short commands for the stand and daily development. `make` lists them.
# Written for GNU Make 3.81 (the macOS system make): no 4.x features.

.DEFAULT_GOAL := help
# `check` must stop at the first failing step; under -j its prerequisites would race.
.NOTPARALLEL:

# Development tools run through this interpreter; the recipes `cd back`, so the
# default is absolute. Override with PY=... to use another environment.
PY ?= $(CURDIR)/back/.venv/bin/python
# Interpreter that creates back/.venv. On macOS `python3` is the system 3.9.
PYTHON ?= python3
COMPOSE ?= docker compose
# Not 8001: that port is taken by the stand's backend.
RUN_PORT ?= 8002

# The stand's port, as compose resolves it: the shell environment, then .env.
# Only a plain number (optionally in double quotes) is read; the last definition wins.
FRONTEND_PORT ?= $(shell sed -n 's/^FRONTEND_PORT="\{0,1\}\([0-9][0-9]*\)"\{0,1\}[[:space:]]*$$/\1/p' .env 2>/dev/null | tail -n 1)
# Override for a stand bound to another address (FRONTEND_BIND).
SMOKE_URL ?= http://localhost:$(or $(FRONTEND_PORT),8080)

# Directories whose comments must not reference internal documents or requirement ids.
COMMENT_DIRS ?= back/src back/openapi

PY311_CHECK := import sys; sys.exit(sys.version_info < (3, 11))

.PHONY: help up down ps logs reset smoke \
	install run lint fmt typecheck test test-unit test-integration check-comments check gen-api

help:
	@awk 'BEGIN {FS = ":.*## "} \
		/^##@ / {printf "\n%s\n", substr($$0, 5)} \
		/^[a-zA-Z0-9_.-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

##@ Стенд (Docker Compose)

up: ## Поднять стенд в фоне (при первом запуске создаёт .env из .env.example)
	@test -f .env || { cp .env.example .env && echo "Создан .env из .env.example"; }
	$(COMPOSE) up -d --build

down: ## Остановить стенд (данные сохраняются)
	$(COMPOSE) down

ps: ## Статус сервисов
	$(COMPOSE) ps

logs: ## Логи в реальном времени; один сервис — make logs s=backend
	$(COMPOSE) logs -f $(s)

reset: ## ОСТОРОЖНО: удалить данные БД и граф OSRM (без вопроса — CONFIRM=yes)
	@[ "$(CONFIRM)" = yes ] || { \
		printf 'Удалить данные БД и граф OSRM? [y/N] '; read answer; \
		[ "$$answer" = y ] || { echo "Отменено"; exit 1; }; }
	$(COMPOSE) down -v

smoke: ## Проверить поднятый стенд через фронтенд-прокси
	@code=$$(curl -s --noproxy '*' --max-time 10 -o /dev/null -w '%{http_code}' "$(SMOKE_URL)/health"); \
		echo "GET /health -> $$code (ожидается 200)"; test "$$code" = 200
	@code=$$(curl -s --noproxy '*' --max-time 10 -o /dev/null -w '%{http_code}' "$(SMOKE_URL)/api/v1/regions"); \
		echo "GET /api/v1/regions -> $$code (ожидается 501)"; test "$$code" = 501

##@ Разработка (back/)

install: ## Создать back/.venv (Python 3.11+, другой — PYTHON=...) и поставить dev-зависимости
	@if [ -x back/.venv/bin/python ]; then \
		back/.venv/bin/python -c "$(PY311_CHECK)" || { \
			echo "back/.venv создан на Python ниже 3.11: rm -rf back/.venv и make install PYTHON=python3.11"; \
			exit 1; }; \
	else \
		$(PYTHON) -c "$(PY311_CHECK)" || { \
			echo "$(PYTHON) — Python ниже 3.11: make install PYTHON=python3.11"; exit 1; }; \
		$(PYTHON) -m venv back/.venv; \
	fi
	back/.venv/bin/python -m pip install -e './back[dev]'

run: ## Локальный backend на RUN_PORT с автоперезагрузкой (настройки — back/.env)
	cd back && LOG_FORMAT=console $(PY) -m uvicorn src.main:app --reload --port $(RUN_PORT) --no-access-log

lint: ## ruff check
	cd back && $(PY) -m ruff check .

fmt: ## ruff format
	cd back && $(PY) -m ruff format .

typecheck: ## mypy
	cd back && $(PY) -m mypy src

test: ## Все тесты
	cd back && $(PY) -m pytest -q

test-unit: ## Тесты без внешних сервисов
	cd back && $(PY) -m pytest -m 'not integration' -q

test-integration: ## Тесты с PostgreSQL и OSRM
	cd back && $(PY) -m pytest -m integration -q

# grep exits 1 when nothing is found — the only passing outcome; 0 (found) and
# 2 (grep error) both fail the target. Binary files and bytecode are skipped.
check-comments: ## Комментарии без ссылок на внутренние документы и номера требований
	@grep -rnIE --exclude-dir=__pycache__ '\.md\b|§|AGENTS|\b(BR|FR|NFR)-[0-9]+' $(COMMENT_DIRS); \
		status=$$?; \
		if [ $$status -eq 0 ]; then echo "check-comments: уберите ссылки выше"; fi; \
		test $$status -eq 1

check: lint typecheck test-unit check-comments ## lint + typecheck + test-unit + check-comments

# The output is byte-stable only for the generator version pinned in back/pyproject.toml.
gen-api: ## Перегенерировать Pydantic-схемы по openapi/openapi.yaml
	cd back && $(PY) -m datamodel_code_generator \
		--input openapi/openapi.yaml --input-file-type openapi \
		--output-model-type pydantic_v2.BaseModel --field-constraints --use-annotated \
		--target-python-version 3.11 --disable-timestamp --formatters ruff-format ruff-check \
		--output src/api/schemas/generated/models.py
