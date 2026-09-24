# Backend

FastAPI-сервис планирования маршрутов выездных инженеров. Контракт API — [`specs/openapi.yaml`](../specs/openapi.yaml) и общие компоненты [`specs/common.yaml`](../specs/common.yaml) в корне репозитория (один контракт для backend и фронтенда), сценарии вызовов — [`src/api/routes/sequence_diagrams.md`](src/api/routes/sequence_diagrams.md).

## Установка и запуск

Команды — из корня репозитория (полный список — `make`):

```bash
make install                   # back/.venv на Python 3.11+ и dev-зависимости
cp back/.env.example back/.env # DATABASE_URL уже указывает на БД стенда; OSRM_URL — по необходимости
make run                       # uvicorn --reload на :8002 (RUN_PORT), LOG_FORMAT=console
```

`make run` запускает uvicorn с `--no-access-log`: HTTP-запросы логирует собственная middleware приложения одной структурной записью, а не встроенный access-лог uvicorn. При ручном запуске флаг тоже обязателен.

Весь стенд (БД, миграции, OSRM, backend, фронтенд) поднимается через Docker Compose — `make up`, см. [корневой README](../README.md#быстрый-старт). Локальный `make run` работает с БД поднятого стенда: она опубликована на `127.0.0.1:${DB_PORT}`, схему к этому моменту уже применил сервис `migrate`.

## Тесты и проверки

```bash
make check             # ruff check + mypy + unit-тесты + проверка комментариев — то же, что гейт перед коммитом
make test-integration  # контрактные тесты и тесты схемы БД: PostGIS поднимается сам через testcontainers, нужен запущенный Docker
make test              # все тесты
```

Описание тестов по слоям — [`tests/tests_readme.md`](tests/tests_readme.md).

## Устройство

- `src/config.py` — настройки (`pydantic-settings`). `Settings` приложения читаются из переменных окружения и `.env`; `MAX_REQUEST_BODY_BYTES` — предел тела запроса в байтах, по умолчанию 10 МБ. `MigrationSettings` процесса миграций — только из окружения: адрес владельца схемы (`MIGRATION_DATABASE_URL`) в настройки приложения не попадает.
- `src/logging.py` — структурированное логирование (`structlog`): JSON или человекочитаемый вывод по `LOG_FORMAT`, идентификатор запроса и идентификатор длительной операции (`run_id`) как поля записи, а не текст. Строки самого uvicorn выходят в том же формате; его access-лог выключен.
- `src/api/deps.py` — `Depends`-фабрики инфраструктуры: пул соединений БД, HTTP-клиент к OSRM.
- `src/app.py` — сборка приложения: настройка логирования, `lifespan` (создание/закрытие пула и клиента), регистрация роутеров и обработчиков ошибок, логирующая middleware (по записи `http_request_finished` на запрос; успешная проба `/health` — на уровне `debug`; запрос, не дошедший ни до одного роута, — с `path="<unmatched>"`).
- `src/errors.py` — доменные исключения без знания об HTTP: `InvalidInput` (с `message` или `fields`), `NotFound`, `Conflict`, `DependencyUnavailable` (зависимость недоступна, повтор может помочь), `DatabaseFailure` (БД отвергла запрос, повтор не поможет); у каждого `reason` для лога и бизнес-параметры `params`. Доменные ошибки операций — их наследники.
- `src/api/errors.py` — единственное место, где собирается ответ ошибки. Тело есть только у `400` (`{"message": ...}` или `{"fields": [{"name", "message"}]}`, тексты на русском, не больше 20 полей); `404`, `405`, `409`, `413`, `500`, `501`, `503` — без тела, текст для пользователя строит фронтенд по операции и коду. Ошибка валидации запроса — `400`, а не `422`, запись `request_validation_failed` с именами полей без значений; `DatabaseFailure` — `500` без повторной записи; непредусмотренное исключение — `500` и запись `unhandled_error` со стеком. Бизнес-ошибку логирует маршрут (`<операция>_failed`), ошибку БД или OSRM — место её возникновения; обработчик их повторно не пишет. Все ветки — в [диаграмме](src/api/routes/sequence_diagrams.md#ошибки-любой-операции--единый-обработчик).
- `src/repository/db.py` — `run_query`, граница между репозиторием и драйвером БД: ошибка драйвера пишется в лог одной записью `db_query_failed` (имя запроса и `sqlstate`, без параметров и текста SQL) и превращается в `DependencyUnavailable` (`503`: потеря соединения, нет свободного соединения в пуле, таймаут, взаимная блокировка) или `DatabaseFailure` (`500`: нарушено ограничение, неверные данные).
- `alembic/` — миграции схемы БД на чистом SQL (`alembic/versions/`, новая ревизия — `python -m alembic revision -m "<slug>"` из `back/`). `alembic/env.py` берёт адрес из `MIGRATION_DATABASE_URL` и пишет в том же JSON-формате, что приложение. Ревизия создаёт и роли: `app_rw` — приложение, только данные, без права менять схему; `app_ro` — ручные запросы, только чтение; пароли — из `APP_RW_PASSWORD`/`APP_RO_PASSWORD`. Всё время в БД — `TIMESTAMP(0)` без часового пояса, местное время региона. Как стенд применяет миграции — [диаграмма](alembic/sequence_diagrams.md).
- `src/api/body_limit.py` — ASGI-middleware предела тела: `413` без тела и с `Connection: close` сразу по `Content-Length` или при чтении тела без него; тело не буферизуется.
- `src/api/routes/not_implemented.py` — заглушка: любой запрос под `/api/v1`, не совпавший с реализованной операцией, получает `501` без тела; регистрируется последней и в контракт не входит.
- `src/api/routes/` — рукописные роутеры; `src/api/schemas/generated/` — Pydantic-схемы, сгенерированные командой `make gen-api` (`models.py` — из `specs/openapi.yaml`, `common.py` — из `specs/common.yaml`, по запуску генератора на файл), не редактируются руками.
