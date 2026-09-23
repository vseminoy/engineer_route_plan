# Тесты backend (`back/`)

## Содержание

- [`src/config.py` — Settings](#srcconfigpy--settings)
- [`src/logging.py` — логирование с run_id](#srcloggingpy--логирование-с-run_id)
- [`src/errors.py` — доменные исключения](#srcerrorspy--доменные-исключения)
- [`src/api/errors.py` — единый обработчик ошибок](#srcapierrorspy--единый-обработчик-ошибок)
- [`src/api/body_limit.py` — предел размера тела запроса](#srcapibody_limitpy--предел-размера-тела-запроса)
- [`src/api/deps.py` — Depends-фабрики БД/OSRM](#srcapidepspy--depends-фабрики-бдosrm)
- [`src/app.py` — app factory и lifespan](#srcapppy--app-factory-и-lifespan)
- [`api` — GET /health](#api--get-health)
- [`api` — заглушка /api/v1/{path}](#api--заглушка-apiv1path)
- [Стенд Docker Compose — smoke](#стенд-docker-compose--smoke)
- [`Makefile` — команды проекта](#makefile--команды-проекта)
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
| `test_settings_max_request_body_bytes_default` | `MAX_REQUEST_BODY_BYTES` не задан | `max_request_body_bytes == 10485760` (10 МБ) |
| `test_settings_max_request_body_bytes_from_env` | `MAX_REQUEST_BODY_BYTES=2048` | `max_request_body_bytes == 2048` |
| `test_settings_rejects_non_positive_body_limit` (параметризован: `0`, `-1`) | `MAX_REQUEST_BODY_BYTES` не больше нуля | `pydantic.ValidationError` — нулевой предел отбивал бы любой запрос с телом |

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
| `test_configure_logging_drops_uvicorn_duplicate_of_unhandled_error` | `LOGGING_CONFIG` uvicorn, `configure_logging(settings)` дважды; в `uvicorn.error` пишутся `"Exception in ASGI application\n"` со стеком и другая ошибка | выходит только другая ошибка: необработанное исключение уже записано `unhandled_error`, второй записи со стеком нет; фильтр на логгере один |
| `test_configure_logging_keeps_uvicorn_access_log_off` | тот же `LOGGING_CONFIG`, затем `configure_logging(settings)` и запись в `uvicorn.access` | `uvicorn.access` не видит ни одного handler (`hasHandlers() is False` — по этой проверке uvicorn включает свой access-лог), вывод пуст: URL с параметрами в лог не попадает |

> `configure_logging` каждый раз заменяет `root.handlers` целиком — после первого вызова
> (например, внутри `create_app()` в тесте) вывод `caplog`/`pytest` для последующих тестов в
> том же процессе перестаёт быть «дефолтным». Тесты этого модуля и `test_app.py` читают
> вывод напрямую (`capsys`) или через `structlog.testing.capture_logs()`, а не `caplog`, —
> следующий тест логирования делает так же, а не полагается на `caplog`.

## `src/errors.py` — доменные исключения

Файл: `tests/test_errors.py`.

> Мок не нужен: чистые классы исключений без знания об HTTP.

| Test | Scenario | Expected result |
|---|---|---|
| `test_domain_errors_share_app_error_base` | `InvalidInput`, `NotFound`, `Conflict`, `DependencyUnavailable` | каждый — подкласс `AppError` |
| `test_app_error_carries_reason_and_params` | `NotFound(reason="plan_not_found", params={"plan_id": 7})` | `e.reason == "plan_not_found"`, `e.params == {"plan_id": 7}` |
| `test_app_error_params_default_to_empty` | `Conflict(reason="x")` без `params` | `e.params == {}` — маршрут может разворачивать `**e.params` в лог без проверки |
| `test_invalid_input_with_message` | `InvalidInput(reason="file_empty", message="Файл не содержит ни одной заявки")` | `e.message` задан, `e.fields is None` |
| `test_invalid_input_with_fields` | `InvalidInput(reason="window_order", fields=[("window_start", "Начало окна позже его окончания")])` | `e.fields` — список пар «имя параметра + текст», `e.message is None` |
| `test_invalid_input_requires_exactly_one_of_message_fields` (параметризован: ни одного; оба; пустой `fields`) | конструктор `InvalidInput` | `ValueError` — тело `400` содержит ровно одно из двух полей |
| `test_domain_error_subclass_keeps_base_mapping` | `class PlanNotFound(NotFound)`, экземпляр | `isinstance(e, NotFound)` — доменный наследник попадает в код своего базового класса |

## `src/api/errors.py` — единый обработчик ошибок

Файл: `tests/api/test_errors.py`.

> Замена стабами: сервис и репозиторий — тестовые роуты на отдельном приложении
> `create_app()` + временный `APIRouter`, которые поднимают нужное исключение; реальных
> БД и OSRM нет. Логи — разбором JSON-строк stderr (`capsys`), а не
> `structlog.testing.capture_logs()`: тот подменяет цепочку процессоров, и `request_id` из
> контекста в записи не попадает. `500` — `TestClient(..., raise_server_exceptions=False)`.

### Сопоставление исключения и кода

| Test | Scenario | Expected result |
|---|---|---|
| `test_invalid_input_message_returns_400_with_message` | роут поднимает `InvalidInput(message="Файл не содержит ни одной заявки")` | `400`, тело `{"message": "Файл не содержит ни одной заявки"}` — валидно по `ValidationError` из `specs/common.yaml`; есть `X-Request-ID` |
| `test_invalid_input_fields_returns_400_with_fields` | роут поднимает `InvalidInput(fields=[("window_start", "Начало окна позже его окончания")])` | `400`, тело `{"fields": [{"name": "window_start", "message": "Начало окна позже его окончания"}]}` |
| `test_bodyless_error_codes` (параметризован: `NotFound`→`404`, `Conflict`→`409`, `DependencyUnavailable`→`503`, доменный наследник `PlanNotFound(NotFound)`→`404`) | роут поднимает исключение | код по таблице, тело пустое (`content == b""`), заголовка `Content-Type: application/json` нет, `X-Request-ID` есть |
| `test_unmapped_app_error_returns_500` | роут поднимает голый `AppError(reason="x")` (класса нет в таблице) | `500` без тела и запись `unhandled_error` — неописанная ошибка не превращается молча в `4xx` |
| `test_app_error_is_not_logged_by_handler` | роут поднимает `NotFound` | в захваченных событиях нет записи от обработчика (ни `unhandled_error`, ни `request_validation_failed`): бизнес-ошибку логирует маршрут, обработчик только отвечает |

### Ошибка валидации запроса (`RequestValidationError`)

> Роут с тестовой моделью тела (`additionalProperties: false` → `extra="forbid"`, строка с
> `max_length`, число с `ge`/`le`, вложенный список объектов) и query-параметром.

| Test | Scenario | Expected result |
|---|---|---|
| `test_validation_error_returns_400_not_422` | в теле нет обязательного поля | `400` (не `422`), тело `{"fields": [...]}`, `X-Request-ID` есть |
| `test_field_name_drops_body_and_query_prefix` (параметризован: поле тела, query-параметр) | невалидное поле тела `region`; невалидный query `limit` | `name == "region"` / `name == "limit"` — без `body`/`query` из `loc` Pydantic |
| `test_nested_field_name_uses_dots_and_brackets` | невалидно `engineers[2].skills` во вложенном списке | `name == "engineers[2].skills"` |
| `test_every_invalid_field_is_reported` | два поля невалидны одновременно | в `fields` две записи, по одной на поле |
| `test_pydantic_message_is_translated` (параметризован по `type`: `missing`, `string_too_long`, `string_too_short`, `greater_than_equal`, `less_than_equal`, `int_parsing`, `extra_forbidden`, `enum`, `string_pattern_mismatch`) | нарушение соответствующего ограничения | `message` — непустой русский текст продукта (содержит кириллицу, не совпадает с английским `msg` Pydantic); у ограничений с пределом в тексте есть число предела |
| `test_unknown_pydantic_type_gets_generic_message` | ошибка валидации с `type`, которого нет в таблице перевода (тестовый валидатор с собственным `type`) | `message == "Некорректное значение"` |
| `test_malformed_json_body_returns_400_message` | тело `{"region": ` (обрезанный JSON) | `400`, тело `{"message": ...}` с русским текстом о некорректном JSON — ошибку нельзя привязать к полю |
| `test_malformed_json_is_logged_without_field_names` | то же тело | в записи `request_validation_failed` `fields == []` — смещение в байтах из `loc` не выдаётся за имя поля |
| `test_undecodable_body_returns_400_message` | JSON-тело `\xff\xfe{"a":1}` (не UTF-8): `400` поднимает сам FastAPI | `400`, тело `{"message": "Тело запроса отсутствует или имеет неверный формат"}` — у `400` тело есть всегда |
| `test_validation_errors_are_capped` | `ids` — список из 100 невалидных элементов | в `fields` 20 записей; в записи `request_validation_failed` 20 имён и `errors_total == 100` — ответ и лог не растут вместе с телом |
| `test_long_field_name_is_truncated` | лишнее поле тела с именем из 500 символов | `name` в `fields` обрезан до 200 символов |
| `test_validation_error_is_logged_without_values` | тело с невалидными `region="Секретный адрес"` и `limit=-1` | одна запись `request_validation_failed` уровня `warning` с `path` — шаблоном роута и `fields == ["limit", "region"]` (только имена); значения полей не встречаются ни в одном поле записи |

### Ответы Starlette и непредусмотренные ошибки

| Test | Scenario | Expected result |
|---|---|---|
| `test_unknown_path_returns_404_without_body` | `GET /unknown` на `create_app()` | `404`, тело пустое (не `{"detail": "Not Found"}`), `X-Request-ID` есть |
| `test_unmatched_request_logs_marker_not_path` | `GET /unknown/user@mail.ru` | запись `http_request_finished` с `path == "<unmatched>"`; присланный путь в запись не попадает |
| `test_method_not_allowed_returns_405_without_body` | `POST /health` на `create_app()` | `405`, тело пустое, заголовок `Allow` сохранён, `X-Request-ID` есть |
| `test_unhandled_exception_returns_500_without_body` | роут поднимает `RuntimeError("boom")` | `500`, тело пустое |
| `test_500_has_request_id_header` | тот же роут, запрос с `X-Request-ID: trace-500` | в ответе `X-Request-ID: trace-500` — обработчик берёт id из контекста, хотя работает снаружи middleware запроса |
| `test_unhandled_exception_is_logged_with_stack` | тот же роут | запись `unhandled_error` уровня `error` с `exc_info` (стек `RuntimeError`) и тем же `request_id`, что в заголовке ответа; текст исключения в ответ не попадает |

### Цепочка логов одной ошибки зависимости (образец для репозиториев и клиентов)

> Тестовый «репозиторий» пишет `db_query_failed` (`query`, `sqlstate`) и поднимает
> `DependencyUnavailable(reason="db_unavailable") from e`; тестовый маршрут `load_sample`
> ловит `AppError`, пишет `load_sample_failed` и пробрасывает. Вызов — через
> `create_app()`, чтобы `request_id` привязала настоящая middleware запроса.

| Test | Scenario | Expected result |
|---|---|---|
| `test_dependency_error_logs_origin_and_route_with_same_request_id` | репозиторий получает исключение драйвера | `503` без тела; ровно две записи об ошибке — `db_query_failed` (уровень `error`, `query`, `sqlstate`) и `load_sample_failed` (уровень `error`, `reason="db_unavailable"`) — с одним и тем же `request_id`, равным `X-Request-ID` ответа; обработчик третьей записи не добавляет |
| `test_client_error_logs_route_failure_at_warning` | маршрут получает `NotFound(reason="sample_not_found", params={"sample_id": 5})` | `404`; запись `load_sample_failed` уровня `warning` с `reason="sample_not_found"`, `sample_id=5` |

## `src/api/body_limit.py` — предел размера тела запроса

Файл: `tests/api/test_body_limit.py`.

> Замена стабами: вместо приложения — тестовое ASGI-приложение, которое читает тело
> через `receive()` и считает полученные байты; предел в тестах — `1024` байта. Сквозные
> проверки — через `create_app()` с `Settings(max_request_body_bytes=1024)` и тестовым
> JSON-роутом; у их `413` есть `X-Request-ID`, значит middleware предела стоит внутри
> middleware запроса.

| Test | Scenario | Expected result |
|---|---|---|
| `test_content_length_over_limit_rejected_without_reading` | `Content-Length: 1025`, тело 1025 байт | `413`, тело пустое, заголовки `Content-Length: 0` и `Connection: close`; тестовое приложение не вызвано, `receive()` не вызывался ни разу |
| `test_content_length_at_limit_passes` | `Content-Length: 1024`, тело 1024 байта | ответ приложения, тело получено целиком |
| `test_chunked_body_over_limit_rejected_while_reading` | без `Content-Length`, тело частями по 512 байт, всего 2048 | `413`, тело пустое; приложению отдано не больше 1024 байт — приём прерван на превышении, тело не буферизуется целиком |
| `test_chunked_body_under_limit_passes` | без `Content-Length`, частями, всего 1000 байт | ответ приложения, тело получено целиком |
| `test_invalid_content_length_falls_back_to_counting` | `Content-Length: abc`, тело 2048 байт частями | `413` — предел не обходится испорченным заголовком |
| `test_request_without_body_passes` | `GET` без тела | ответ приложения |
| `test_over_limit_after_response_started_does_not_send_second_response` | приложение начинает ответ до того, как дочитает тело, и продолжает читать сверх предела | второй `http.response.start` не отправляется; соединение завершается без `413` — ответ уже ушёл |
| `test_non_http_scope_passes_through` | `scope["type"] == "lifespan"` | вызов передан приложению без изменений |
| `test_413_through_app_has_request_id_and_is_logged` (параметризован: с `Content-Length`; chunked — тело генератором, без `Content-Length`) | `POST` JSON-тела 2048 байт на тестовый JSON-роут `create_app()` | `413` без тела, `Content-Length: 0`, `Connection: close`, `X-Request-ID` есть; одна запись `http_request_finished` со `status=413` — в chunked-случае `413` приходит из чтения тела через единый обработчик, а не `400` |

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
| `test_create_app_registers_error_handlers` | `create_app()` | в `app.exception_handlers` есть обработчики `AppError`, `RequestValidationError`, `StarletteHTTPException`, `Exception` |
| `test_create_app_registers_not_implemented_stub_last` | `create_app()` | последний элемент `app.routes` — заглушка `/api/v1/{path:path}`: любой роут, объявленный в фабрике, стоит раньше неё и перекрывает её |

> Request-логирующая middleware (`09-logging.md` → «Контекст запроса», замена access-лога uvicorn):

| Test | Scenario | Expected result |
|---|---|---|
| `test_request_id_header_generated_when_absent` | `GET /health` без заголовка `X-Request-ID` | ответ содержит заголовок `X-Request-ID` с непустым значением |
| `test_request_id_header_echoed_when_provided` | `GET /health` с `X-Request-ID: custom-id` | ответ содержит `X-Request-ID: custom-id` — тот же id, не новый |
| `test_request_id_header_rejects_invalid_value` | `GET /health` с `X-Request-ID: not a valid id!` (не проходит `^[A-Za-z0-9_-]{1,64}$`) | ответный `X-Request-ID` — НЕ эхо клиентского значения, новый сгенерированный id (клиентский вход не идёт в заголовок ответа/лог непровалидированным) |
| `test_http_request_finished_is_logged` | `GET /health` на `create_app()` с `LOG_LEVEL=DEBUG` (`configure_logging` отработал при сборке приложения — JSON на stderr, `capsys`) | среди распарсенных JSON-строк есть событие `http_request_finished` с полями `method="GET"`, `path="/health"`, `status=200`, `duration_ms` — число |
| `test_successful_health_probe_is_not_logged_at_info` | `GET /health` на `create_app()` с уровнем по умолчанию `INFO` | события `http_request_finished` в выводе нет: успешная проба healthcheck пишется на `debug` и не засоряет лог |
| `test_http_request_finished_is_logged_on_unhandled_exception` | необработанное исключение в обработчике (временный `/boom`-роут в тесте), `TestClient(..., raise_server_exceptions=False)` | `500` клиенту; событие `http_request_finished` со `status=500` попадает в лог — запрос не «пропадает» из наблюдаемости, хотя ответ `500` формирует обработчик снаружи middleware |

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

## `Makefile` — команды проекта

> Ручные сценарии из корня репозитория, не часть `pytest`: цели только вызывают готовые
> команды, собственной логики, которую стоило бы покрыть юнит-тестом, у них нет. Ничего
> не мокается; цели стенда работают с настоящим Docker Compose. Проверяется GNU Make 3.81
> (системный на macOS) — возможностей 4.x Makefile не использует.

| Test | Scenario | Expected result |
|---|---|---|
| `make_default_prints_help` | `make` без аргументов | код `0`; список всех целей с описаниями, сгруппированный на «стенд» и «разработка»; у `reset` пометка, что он удаляет данные БД и граф OSRM |
| `make_install_then_check_passes` | чистый клон: `make install && make check` | код `0`; создан `back/.venv`, отработали `lint`, `typecheck`, `test-unit`, `check-comments` |
| `make_install_rejects_old_python` | нет `back/.venv`; `make install PYTHON=/usr/bin/python3` (Python 3.9) | код `≠ 0`, venv не создан, подсказка `PYTHON=python3.11` |
| `make_install_rejects_old_venv` | `back/.venv` создан на Python 3.9; `make install` | код `≠ 0`, подсказка удалить `back/.venv` и повторить с `PYTHON=` |
| `make_check_stops_on_first_failure` | в `back/src` временно добавлен неиспользуемый импорт; `make check` | код `≠ 0`, в выводе ошибка `ruff`; цель не сообщает об успехе |
| `make_check_comments_clean` | `make check-comments` на текущем коде | код `0`, находок нет — отсутствие совпадений у `grep` не считается ошибкой |
| `make_check_comments_covers_specs` | в `description` в `specs/common.yaml` временно добавлена ссылка на `.md`-файл; `make check-comments` | код `≠ 0`, находка в `specs/` выведена — проверка смотрит в `specs/`, а не в прежнее место спеки |
| `make_check_comments_finds_reference` | в комментарий в `back/src` временно добавлены ссылка на `.md`-файл и номер требования; `make check-comments` | код `≠ 0`, выведены файл и строка каждой находки |
| `make_quality_targets_wrap_profile_commands` | `make -n lint typecheck test test-unit test-integration` | в `back/` через `$(PY) -m` выполняются `ruff check .`, `mypy src`, `pytest -q`, `pytest -m 'not integration' -q`, `pytest -m integration -q` — те же команды, что проверяет гейт перед коммитом |
| `make_tools_from_venv_overridable` | `make -n lint` и `make -n lint PY=/usr/bin/python3` | по умолчанию инструменты берутся из `back/.venv/bin`, с `PY=...` — через указанный интерпретатор |
| `make_gen_api_is_reproducible` | `make gen-api` на неизменённых `specs/openapi.yaml` и `specs/common.yaml`, затем `git diff --exit-code back/src/api/schemas/generated` | код `0` у обеих команд, diff пуст |
| `make_gen_api_generates_common_schemas` | `make gen-api` | в `back/src/api/schemas/generated/` есть модели и из `specs/openapi.yaml` (`HealthStatus`), и из `specs/common.yaml` (`ValidationError`, `RequestMessage`, `FieldErrors`, `FieldError`) — каждая спека своим запуском генератора, в свой модуль |
| `make_up_then_smoke_passes` | нет `.env`: `make up && make smoke` | `.env` создан из `.env.example` (существующий `make up` не трогает), образы пересобраны, стенд поднят; `smoke` печатает `200` для `/health` и `501` для `/api/v1/regions` через фронтенд-прокси на `FRONTEND_PORT` из `.env`, код `0` |
| `make_smoke_reads_port_from_env` | в `.env` `FRONTEND_PORT="8090"`, ниже повторно `FRONTEND_PORT=8091`; затем `FRONTEND_PORT=8090;id`; `make -n smoke` | в первом случае URL на `:8091` (последнее определение); во втором значение не принято, URL на `:8080` — в команду попадает только число |
| `make_smoke_fails_when_stand_is_down` | `make down && make smoke` | код `≠ 0`, из вывода понятно, какая проверка не прошла |
| `make_logs_single_service` | `make logs s=backend` | потоковый вывод (`-f`) только сервиса `backend`; без `s=` — всех сервисов |
| `make_reset_asks_confirmation` | `make reset`, ответ `n` (или пустой ввод) | код `≠ 0`, «Отменено», стенд и volume'ы не тронуты |
| `make_reset_removes_volumes` | `make reset CONFIRM=yes`, затем `docker volume ls` | без вопроса; стенд остановлен, volume'ов стенда (данные БД, граф OSRM) больше нет |
| `make_run_uses_free_port` | `make -n run`; `make -n run RUN_PORT=9000` | uvicorn на `--port 8002` (не на порту backend стенда), с `RUN_PORT` — на указанном |

## `<integration suite>` — контрактные тесты

> Запускается отдельно от unit-набора (`commands.test_integration`), помечен
> `@pytest.mark.integration` — по фиксированной для `api (контрактный)` классификации
> профиля, независимо от того, обращаются ли операции спеки к БД.
> `schemathesis` строит кейсы из `specs/openapi.yaml` (ссылки на `specs/common.yaml`
> разрешаются от корня) и прогоняет их против поднятого приложения в двух режимах —
> позитивном и негативном; пишется один раз на всё приложение, а не по эндпоинту, и
> растёт вместе со спекой.

| Test | Scenario | Expected result |
|---|---|---|
| `test_api_conforms_to_openapi_schema` | `schemathesis.from_path("specs/openapi.yaml")` с методами генерации positive + negative, все операции спеки | каждый сгенерированный кейс: код ответа объявлен у операции, тело соответствует схеме (у кодов без тела — пустое), заголовок `X-Request-ID` есть; запрос, нарушающий ограничение спеки, получает `400`, а не `422` |
