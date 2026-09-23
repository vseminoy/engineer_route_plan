# Тесты backend (`back/`)

## Содержание

- [`src/config.py` — Settings](#srcconfigpy--settings)
- [`src/logging.py` — логирование с run_id](#srcloggingpy--логирование-с-run_id)
- [`src/api/deps.py` — Depends-фабрики БД/OSRM](#srcapidepspy--depends-фабрики-бдosrm)
- [`src/app.py` — app factory и lifespan](#srcapppy--app-factory-и-lifespan)
- [`api` — GET /health](#api--get-health)
- [`api` — заглушка /api/v1/{path}](#api--заглушка-apiv1path)
- [Стенд Docker Compose — smoke](#стенд-docker-compose--smoke)
- [`<integration suite>` — контрактные тесты](#integration-suite--контрактные-тесты)

---

## `src/config.py` — Settings

> Мок не нужен: чистая проверка парсинга `pydantic-settings` из переменных окружения.

| Test | Scenario | Expected result |
|---|---|---|
| `test_settings_reads_from_env` | заданы `DATABASE_URL`, `OSRM_URL`, `APP_MODE=demo` в окружении | `Settings()` собирает поля с этими значениями |
| `test_settings_rejects_unknown_app_mode` | `APP_MODE=production` (не `demo`/`full`) | `pydantic.ValidationError` |
| `test_settings_missing_required_var` | `DATABASE_URL` не задан | `pydantic.ValidationError` |
| `test_settings_rejects_unknown_log_format` | `LOG_FORMAT=xml` (не `json`/`console`) | `pydantic.ValidationError` |

## `src/logging.py` — логирование с run_id (`structlog`, `09-logging.md`)

> Мок не нужен: проверка через `structlog.testing.capture_logs()` — по событию и
> полям, а не по тексту (`09-logging.md` → «Тесты»).

| Test | Scenario | Expected result |
|---|---|---|
| `test_new_run_id_is_unique` | два последовательных вызова `new_run_id()` | значения не совпадают |
| `test_run_id_context_binds_run_id_to_log_events` | лог пишется внутри `run_id_context("abc123")` | захваченное событие содержит `run_id == "abc123"` |
| `test_run_id_context_unbinds_on_exit` | лог пишется после выхода из `run_id_context(...)` | у захваченного события нет поля `run_id` (не «протекает» в следующие события) |
| `test_log_event_without_context_has_no_run_id_field` | лог пишется вне какого-либо `run_id_context` | у события нет поля `run_id` — структурному логу не нужен плейсхолдер вместо отсутствующего поля |
| `test_configure_logging_json_format_produces_one_json_line_per_record` | `configure_logging(settings)` с `log_format="json"`, лог пишется и через `structlog`, и через сторонний `logging.getLogger(...)` (эмулирует uvicorn/psycopg) | оба выхода — по одной валидной JSON-строке на запись, одного формата (`09-logging.md` → «Тесты») |
| `test_configure_logging_console_format_is_human_readable_not_json` | `configure_logging(settings)` с `log_format="console"` | вывод содержит имя события как текст, но НЕ парсится как JSON — веткам json/console не перепутаться местами незаметно |
| `test_configure_logging_routes_uvicorn_loggers_to_json` | к логгерам применён `uvicorn.config.LOGGING_CONFIG` (текстовые handlers на `uvicorn` и `uvicorn.access`, `propagate=False`), затем `configure_logging(settings)` с `log_format="json"` и запись в `uvicorn.error` | ровно одна строка вывода, и она — JSON с `event == "Started server process"`: стартовые строки uvicorn выходят в том же формате, что и записи приложения |
| `test_configure_logging_keeps_uvicorn_access_log_off` | тот же `LOGGING_CONFIG`, затем `configure_logging(settings)` и запись в `uvicorn.access` | `uvicorn.access` не видит ни одного handler (`hasHandlers() is False` — по этой проверке uvicorn включает свой access-лог), вывод пуст: URL с параметрами в лог не попадает |

> `configure_logging` каждый раз заменяет `root.handlers` целиком — после первого вызова
> (например, внутри `create_app()` в тесте) вывод `caplog`/`pytest` для последующих тестов в
> том же процессе перестаёт быть «дефолтным». Тесты этого модуля и `test_app.py` читают
> вывод напрямую (`capsys`) или через `structlog.testing.capture_logs()`, а не `caplog`, —
> следующий тест логирования делает так же, а не полагается на `caplog`.

## `src/api/deps.py` — Depends-фабрики БД/OSRM

> Замена стабами: пул соединений БД (`psycopg_pool.AsyncConnectionPool` — фейковый пул с
> контролируемым `connection()`), `httpx.AsyncClient` (реальный сетевой вызов не выполняется).

| Test | Scenario | Expected result |
|---|---|---|
| `test_get_db_connection_yields_and_releases` | фабрика вызвана как `Depends` с фейковым пулом в `app.state` | соединение из пула отдано генератором и возвращено в пул после выхода из блока |
| `test_get_db_connection_pool_not_opened_at_import` | создание пула (`open=False`), `pool.open()` не вызывается | конструктор пула не выполняет сетевого подключения — приложение поднимается без доступной БД |
| `test_get_osrm_client_returns_shared_client` | фабрика вызвана как `Depends`, клиент уже создан в `lifespan` и лежит в `app.state.osrm_client` | возвращает тот же объект `httpx.AsyncClient` (`base_url == settings.osrm_url`), не создаёт новый |
| `test_get_osrm_client_not_closed_per_request` | выход из генератора после одного вызова зависимости | `aclose()` клиента НЕ вызывается — клиент общий на всё приложение, закрывается только в `lifespan`-shutdown (переоткрытие TCP-соединения на каждый запрос убило бы смысл `keep-alive` к OSRM) |

## `src/app.py` — app factory и lifespan

> Замена стабами: конструктор пула БД и конструктор `httpx.AsyncClient` (проверяем, что
> `lifespan` их вызывает и потом закрывает, а не что они реально открывают соединения).

| Test | Scenario | Expected result |
|---|---|---|
| `test_lifespan_creates_and_opens_db_pool_without_waiting` | приложение поднято через `lifespan` (`asgi-lifespan`/`TestClient`) | `app.state.db_pool` создан, `pool.open(wait=False)` вызван один раз — старт не блокируется недоступностью БД |
| `test_lifespan_creates_osrm_client` | запуск `lifespan` | `app.state.osrm_client` — `httpx.AsyncClient` с `base_url == settings.osrm_url` |
| `test_lifespan_closes_pool_and_client_on_shutdown` | завершение `lifespan` | `pool.close()` и `osrm_client.aclose()` вызваны по одному разу |
| `test_create_app_registers_health_route` | `create_app()` | в `app.routes` присутствует `GET /health` |
| `test_create_app_registers_not_implemented_stub_last` | `create_app()` | последний элемент `app.routes` — заглушка `/api/v1/{path:path}`: любой роут, объявленный в фабрике, стоит раньше неё и перекрывает её |

> Request-логирующая middleware (`09-logging.md` → «Контекст запроса», замена access-лога uvicorn):

| Test | Scenario | Expected result |
|---|---|---|
| `test_request_id_header_generated_when_absent` | `GET /health` без заголовка `X-Request-ID` | ответ содержит заголовок `X-Request-ID` с непустым значением |
| `test_request_id_header_echoed_when_provided` | `GET /health` с `X-Request-ID: custom-id` | ответ содержит `X-Request-ID: custom-id` — тот же id, не новый |
| `test_request_id_header_rejects_invalid_value` | `GET /health` с `X-Request-ID: not a valid id!` (не проходит `^[A-Za-z0-9_-]{1,64}$`) | ответный `X-Request-ID` — НЕ эхо клиентского значения, новый сгенерированный id (клиентский вход не идёт в заголовок ответа/лог непровалидированным) |
| `test_http_request_finished_is_logged` | `GET /health` на `create_app()` с `LOG_LEVEL=DEBUG` (`configure_logging` отработал при сборке приложения — JSON на stderr, `capsys`) | среди распарсенных JSON-строк есть событие `http_request_finished` с полями `method="GET"`, `path="/health"`, `status=200`, `duration_ms` — число |
| `test_successful_health_probe_is_not_logged_at_info` | `GET /health` на `create_app()` с уровнем по умолчанию `INFO` | события `http_request_finished` в выводе нет: успешная проба healthcheck пишется на `debug` и не засоряет лог |
| `test_http_request_finished_is_logged_on_unhandled_exception` | необработанное исключение в обработчике (временный `/boom`-роут в тесте — исключение выброшено уже после ответа стандартных обработчиков, обработчика ошибок в проекте ещё нет), `TestClient(..., raise_server_exceptions=False)` | `500` клиенту; событие `http_request_finished` со `status=500` всё равно попадает в лог — запрос не «пропадает» из наблюдаемости при необработанном исключении |

## `api` — GET /health

> Зависимостей нет: обработчик не использует `Depends` на БД/OSRM, стабы не нужны.

| Test | Scenario | Expected result |
|---|---|---|
| `test_get_health_returns_ok` | `GET /health` | `200`, тело `{"status": "ok", "version": "<info.version>"}` |
| `test_get_health_content_type_is_json` | `GET /health` | заголовок `Content-Type: application/json` |

## `api` — заглушка /api/v1/{path}

Файл: `tests/api/test_not_implemented.py`.

> Зависимостей нет: заглушка не использует `Depends` на БД/OSRM, стабы не нужны.
> Порядок регистрации проверяется на отдельном `FastAPI()` с тестовым роутом
> `GET /api/v1/regions`, объявленным до заглушки, — в самом приложении ни одной
> операции под `/api/v1` пока нет.

| Test | Scenario | Expected result |
|---|---|---|
| `test_unimplemented_path_returns_501_without_body` | `GET /api/v1/regions` на `create_app()` | `501`, тело пустое (`content == b""`), заголовка `Content-Type: application/json` нет |
| `test_stub_answers_any_method` (параметризован: `GET`, `POST`, `PATCH`, `DELETE`) | запрос методом на `/api/v1/plan/1/replan` | `501`, тело пустое |
| `test_stub_answers_nested_and_root_paths` (параметризован: `/api/v1/`, `/api/v1/tickets/42/status`) | `GET` по пути | `501`, тело пустое — заглушка ловит путь любой глубины под префиксом |
| `test_implemented_route_takes_precedence_over_stub` | на `FastAPI()` подключён роутер с `GET /api/v1/regions` → `200 []`, затем заглушка; запросы `GET /api/v1/regions` и `GET /api/v1/engineers` | первый — `200 []` от роута, второй — `501` от заглушки |
| `test_wrong_method_on_implemented_path_returns_501` | тот же `FastAPI()` с `GET /api/v1/regions` и заглушкой; `POST /api/v1/regions` | `501` без тела, а не `405`: полное совпадение пути и метода даёт заглушка |
| `test_path_outside_api_prefix_returns_404` | `GET /unknown` и `GET /api/v2/regions` | `404`: заглушка ограничена префиксом `/api/v1` |
| `test_health_is_not_shadowed_by_stub` | `GET /health` на `create_app()` | `200` от health-роута |
| `test_stub_is_absent_from_openapi_schema` | `create_app().openapi()` | в `paths` нет ни одного пути с префиксом `/api/v1` — заглушка не часть контракта и не попадает в контрактные тесты |
| `test_stub_request_is_logged_with_request_id` | `GET /api/v1/regions` на `create_app()` (JSON на stderr, `capsys`) | ответ содержит `X-Request-ID`; в логе событие `http_request_finished` со `status=501`, `path="/api/v1/{path:path}"` (шаблон, а не запрошенный путь) и тем же `request_id` |

## Стенд Docker Compose — smoke

> Ручной сценарий из корневого `README.md`, не часть `pytest`: поднимает настоящие
> контейнеры (`db`, `osrm-prepare`, `osrm`, `backend`, `frontend`), ничего не мокается.
> Запросы идут через nginx фронтенда (`http://localhost:8080`).

| Test | Scenario | Expected result |
|---|---|---|
| `smoke_compose_up` | `cp .env.example .env && docker compose up -d` на чистой машине | `db` и `backend` — `healthy`, `frontend` отвечает; `osrm-prepare` готовит граф или сразу завершается, если граф уже есть в volume |
| `smoke_health_via_proxy` | `curl -i http://localhost:8080/health` | `200`, `{"status": "ok", ...}` — отвечает и пока `osrm-prepare` ещё работает |
| `smoke_unimplemented_via_proxy` | `curl -i http://localhost:8080/api/v1/regions` | `501`, тело пустое, есть заголовок `X-Request-ID` |
| `smoke_body_limit_via_proxy` | `POST /api/v1/data/upload` с телом больше `MAX_REQUEST_BODY_BYTES` | `413` от nginx, запрос не доходит до backend (в `docker compose logs backend` нет записи о нём) |
| `smoke_backend_logs_are_json` | `docker compose logs --no-log-prefix backend` | каждая строка — один JSON-объект; у записи `http_request_finished` есть `request_id` |
| `smoke_spa_fallback` | `curl -i http://localhost:8080/plan/1` (клиентский маршрут React) | `200`, отдаётся `index.html` |

## `<integration suite>` — контрактные тесты

> Запускается отдельно от unit-набора (`commands.test_integration`), помечен
> `@pytest.mark.integration` — по фиксированной для `api (контрактный)` классификации
> профиля, независимо от того, что на этом changeset ни один эндпоинт ещё не обращается к БД.
> `schemathesis` строит кейсы из `openapi/openapi.yaml` и прогоняет их против поднятого
> приложения; пишется один раз на всё приложение, а не по эндпоинту, и будет расти вместе
> со спекой в следующих changeset'ах.

| Test | Scenario | Expected result |
|---|---|---|
| `test_api_conforms_to_openapi_schema` | `schemathesis.from_path("openapi/openapi.yaml")`, все операции спеки (сейчас — только `GET /health`) | каждый сгенерированный кейс: код ответа и тело соответствуют схеме |
