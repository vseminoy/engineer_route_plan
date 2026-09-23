# Backend

FastAPI-сервис планирования маршрутов выездных инженеров. Контракт API — [`openapi/openapi.yaml`](openapi/openapi.yaml), сценарии вызовов — [`src/api/routes/sequence_diagrams.md`](src/api/routes/sequence_diagrams.md).

## Установка и запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # заполнить DATABASE_URL/OSRM_URL реальными значениями
uvicorn src.main:app --port 8001 --no-access-log
```

`--no-access-log` обязателен: HTTP-запросы логирует собственная middleware приложения одной структурной записью, а не встроенный access-лог uvicorn.

Весь стенд (БД, OSRM, backend, фронтенд) поднимается через Docker Compose — см. [корневой README](../README.md#запуск-стенда-docker-compose).

## Тесты

```bash
pytest -q                    # unit
pytest -q -m integration     # контрактные и интеграционные тесты (поднятое приложение, БД/OSRM не нужны для текущего набора)
mypy src
ruff check .
```

## Устройство

- `src/config.py` — настройки (`pydantic-settings`), читаются из переменных окружения/`.env`.
- `src/logging.py` — структурированное логирование (`structlog`): JSON или человекочитаемый вывод по `LOG_FORMAT`, идентификатор запроса и идентификатор длительной операции (`run_id`) как поля записи, а не текст. Строки самого uvicorn выходят в том же формате; его access-лог выключен.
- `src/api/deps.py` — `Depends`-фабрики инфраструктуры: пул соединений БД, HTTP-клиент к OSRM.
- `src/app.py` — сборка приложения: настройка логирования, `lifespan` (создание/закрытие пула и клиента), регистрация роутеров, логирующая middleware (по записи `http_request_finished` на запрос; успешная проба `/health` — на уровне `debug`).
- `src/api/routes/not_implemented.py` — заглушка: любой запрос под `/api/v1`, не совпавший с реализованной операцией, получает `501` без тела; регистрируется последней и в контракт не входит.
- `src/api/routes/` — рукописные роутеры; `src/api/schemas/generated/` — Pydantic-схемы, сгенерированные из `openapi/openapi.yaml` (`datamodel-codegen`), не редактируются руками.
