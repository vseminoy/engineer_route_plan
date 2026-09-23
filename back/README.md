# Backend

FastAPI-сервис планирования маршрутов выездных инженеров. Контракт API — [`openapi/openapi.yaml`](openapi/openapi.yaml), сценарии вызовов — [`src/api/routes/sequence_diagrams.md`](src/api/routes/sequence_diagrams.md).

## Установка и запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # заполнить DATABASE_URL/OSRM_URL реальными значениями
uvicorn src.main:app --no-access-log
```

`--no-access-log` обязателен: HTTP-запросы логирует собственная middleware приложения одной структурной записью, а не встроенный access-лог uvicorn.

## Тесты

```bash
pytest -q                    # unit
pytest -q -m integration     # контрактные и интеграционные тесты (поднятое приложение, БД/OSRM не нужны для текущего набора)
mypy src
ruff check .
```

## Устройство

- `src/config.py` — настройки (`pydantic-settings`), читаются из переменных окружения/`.env`.
- `src/logging.py` — структурированное логирование (`structlog`): JSON или человекочитаемый вывод по `LOG_FORMAT`, идентификатор запроса и идентификатор длительной операции (`run_id`) как поля записи, а не текст.
- `src/api/deps.py` — `Depends`-фабрики инфраструктуры: пул соединений БД, HTTP-клиент к OSRM.
- `src/app.py` — сборка приложения: `lifespan` (создание/закрытие пула и клиента), регистрация роутеров, логирующая middleware.
- `src/api/routes/` — рукописные роутеры; `src/api/schemas/generated/` — Pydantic-схемы, сгенерированные из `openapi/openapi.yaml` (`datamodel-codegen`), не редактируются руками.
