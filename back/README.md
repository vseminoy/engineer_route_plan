# Backend

FastAPI-сервис планирования маршрутов выездных инженеров. Контракт API — [`openapi/openapi.yaml`](openapi/openapi.yaml), сценарии вызовов — [`src/api/routes/sequence_diagrams.md`](src/api/routes/sequence_diagrams.md).

## Установка и запуск

Команды — из корня репозитория (полный список — `make`):

```bash
make install                   # back/.venv на Python 3.11+ и dev-зависимости
cp back/.env.example back/.env # заполнить DATABASE_URL/OSRM_URL
make run                       # uvicorn --reload на :8002 (RUN_PORT), LOG_FORMAT=console
```

`make run` запускает uvicorn с `--no-access-log`: HTTP-запросы логирует собственная middleware приложения одной структурной записью, а не встроенный access-лог uvicorn. При ручном запуске флаг тоже обязателен.

Весь стенд (БД, OSRM, backend, фронтенд) поднимается через Docker Compose — `make up`, см. [корневой README](../README.md#быстрый-старт).

## Тесты и проверки

```bash
make check             # ruff check + mypy + unit-тесты + проверка комментариев — то же, что гейт перед коммитом
make test-integration  # контрактные и интеграционные тесты (поднятое приложение, БД/OSRM не нужны для текущего набора)
make test              # все тесты
```

Описание тестов по слоям — [`tests/tests_readme.md`](tests/tests_readme.md).

## Устройство

- `src/config.py` — настройки (`pydantic-settings`), читаются из переменных окружения/`.env`.
- `src/logging.py` — структурированное логирование (`structlog`): JSON или человекочитаемый вывод по `LOG_FORMAT`, идентификатор запроса и идентификатор длительной операции (`run_id`) как поля записи, а не текст. Строки самого uvicorn выходят в том же формате; его access-лог выключен.
- `src/api/deps.py` — `Depends`-фабрики инфраструктуры: пул соединений БД, HTTP-клиент к OSRM.
- `src/app.py` — сборка приложения: настройка логирования, `lifespan` (создание/закрытие пула и клиента), регистрация роутеров, логирующая middleware (по записи `http_request_finished` на запрос; успешная проба `/health` — на уровне `debug`).
- `src/api/routes/not_implemented.py` — заглушка: любой запрос под `/api/v1`, не совпавший с реализованной операцией, получает `501` без тела; регистрируется последней и в контракт не входит.
- `src/api/routes/` — рукописные роутеры; `src/api/schemas/generated/` — Pydantic-схемы, сгенерированные из `openapi/openapi.yaml` командой `make gen-api`, не редактируются руками.
