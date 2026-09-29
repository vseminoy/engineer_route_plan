# Тесты backend (`back/`)

## Содержание

- [`src/config.py` — Settings](#srcconfigpy--settings)
- [`src/logging.py` — логирование с run_id](#srcloggingpy--логирование-с-run_id)
- [`src/errors.py` — доменные исключения](#srcerrorspy--доменные-исключения)
- [`alembic/versions/5d23f2956ce7_initial_schema.py` — схема БД](#alembicversions5d23f2956ce7_initial_schemapy--схема-бд)
- [`alembic/versions/cb3db41d521a_tickets_type_hd_not_null.py` — тип заявки HD обязателен](#alembicversionscb3db41d521a_tickets_type_hd_not_nullpy--тип-заявки-hd-обязателен)
- [`alembic/env.py` — запуск миграций](#alembicenvpy--запуск-миграций)
- [`src/repository/db.py` — обёртка запросов к БД](#srcrepositorydbpy--обёртка-запросов-к-бд)
- [`src/repository/region_data.py` — замена данных региона](#srcrepositoryregion_datapy--замена-данных-региона)
- [`src/repository/region_lists.py` — чтение бригад и заявок региона](#srcrepositoryregion_listspy--чтение-бригад-и-заявок-региона)
- [`src/repository/tickets.py` — статус заявки](#srcrepositoryticketspy--статус-заявки)
- [`src/service/ticket_file.py` — чтение файла заявок](#srcserviceticket_filepy--чтение-файла-заявок)
- [`src/service/ticket_types.py` — таблица соответствия типов заявок](#srcserviceticket_typespy--таблица-соответствия-типов-заявок)
- [`src/service/regions.py` — конфигурация регионов](#srcserviceregionspy--конфигурация-регионов)
- [`src/service/engineers_generator.py` — генератор демо-бригад](#srcserviceengineers_generatorpy--генератор-демо-бригад)
- [`src/service/geocoding.py` — координаты адресов](#srcservicegeocodingpy--координаты-адресов)
- [`src/service/loader.py` — загрузка данных региона](#srcserviceloaderpy--загрузка-данных-региона)
- [`src/service/region_lists.py` — регионы, бригады и заявки региона](#srcserviceregion_listspy--регионы-бригады-и-заявки-региона)
- [`src/service/ticket_status.py` — переходы статусов заявки](#srcserviceticket_statuspy--переходы-статусов-заявки)
- [`src/service/solver.py` — модель солвера, ступенчатая (лексикографическая) оптимизация](#srcservicesolverpy--модель-солвера-ступенчатая-лексикографическая-оптимизация)
- [`src/service/baseline.py` — baseline FCFS](#srcservicebaselinepy--baseline-fcfs)
- [`src/service/explain.py` — атрибуция причины отказа и объяснения](#srcserviceexplainpy--атрибуция-причины-отказа-и-объяснения)
- [`src/clients/nominatim.py` — клиент Nominatim](#srcclientsnominatimpy--клиент-nominatim)
- [`src/clients/osrm.py` — клиент OSRM](#srcclientsosrmpy--клиент-osrm)
- [`scripts/build_geocache.py` — сборка гео-кэша](#scriptsbuild_geocachepy--сборка-гео-кэша)
- [`src/api/errors.py` — единый обработчик ошибок](#srcapierrorspy--единый-обработчик-ошибок)
- [`src/api/body_limit.py` — предел размера тела запроса](#srcapibody_limitpy--предел-размера-тела-запроса)
- [`src/api/deps.py` — Depends-фабрики БД/OSRM](#srcapidepspy--depends-фабрики-бдosrm)
- [`src/app.py` — app factory и lifespan](#srcapppy--app-factory-и-lifespan)
- [`api` — GET /health](#api--get-health)
- [`api` — GET /api/v1/regions](#api--get-apiv1regions)
- [`api` — GET /api/v1/engineers](#api--get-apiv1engineers)
- [`api` — GET /api/v1/tickets](#api--get-apiv1tickets)
- [`api` — PATCH /api/v1/tickets/{ticket_id}/status](#api--patch-apiv1ticketsticket_idstatus)
- [`api` — POST /api/v1/data/upload, POST /api/v1/data/demo](#api--post-apiv1dataupload-post-apiv1datademo)
- [`api` — заглушка /api/v1/{path}](#api--заглушка-apiv1path)
- [`src/api/schemas/generated/common.py` — LocalDateTime, LocalTime](#srcapischemasgeneratedcommonpy--localdatetime-localtime)
- [Стенд Docker Compose — smoke](#стенд-docker-compose--smoke)
- [`Makefile` — команды проекта](#makefile--команды-проекта)
- [`<integration suite>` — контрактные тесты](#integration-suite--контрактные-тесты)

---

## `src/config.py` — Settings

> Мок не нужен: чистая проверка парсинга `pydantic-settings` из переменных окружения.

| Test | Scenario | Expected result |
|---|---|---|
| `test_settings_reads_from_env` | заданы `DATABASE_URL`, `OSRM_URL_CAR`, `OSRM_URL_FOOT`, `OSRM_URL_BIKE`, `APP_MODE=demo` в окружении | `Settings()` собирает поля с этими значениями |
| `test_settings_rejects_unknown_app_mode` | `APP_MODE=production` (не `demo`/`full`) | `pydantic.ValidationError` |
| `test_settings_missing_required_var` | `DATABASE_URL` не задан | `pydantic.ValidationError` |
| `test_settings_rejects_unknown_log_format` | `LOG_FORMAT=xml` (не `json`/`console`) | `pydantic.ValidationError` |
| `test_settings_max_request_body_bytes_default` | `MAX_REQUEST_BODY_BYTES` не задан | `max_request_body_bytes == 1048576` (1 МБ) |
| `test_migration_settings_reads_from_env` | заданы `MIGRATION_DATABASE_URL`, `LOG_LEVEL`, `LOG_FORMAT` | `MigrationSettings()` собирает поля с этими значениями; `DATABASE_URL` и `OSRM_URL_*` ему не нужны |
| `test_migration_settings_missing_url` | `MIGRATION_DATABASE_URL` не задан | `pydantic.ValidationError` |
| `test_migration_settings_ignore_env_file` | в текущем каталоге `.env` с `MIGRATION_DATABASE_URL`, в окружении его нет | `pydantic.ValidationError`: адрес владельца схемы берётся только из окружения процесса миграции, не из `.env` приложения |
| `test_settings_ignore_migration_vars_in_env` | в окружении `MIGRATION_DATABASE_URL`, `APP_RW_PASSWORD`, `APP_RO_PASSWORD` рядом с обычными переменными | `Settings()` собирается, этих полей у него нет — приложение не получает адрес владельца схемы |
| `test_settings_max_request_body_bytes_from_env` | `MAX_REQUEST_BODY_BYTES=2048` | `max_request_body_bytes == 2048` |
| `test_settings_rejects_non_positive_body_limit` (параметризован: `0`, `-1`) | `MAX_REQUEST_BODY_BYTES` не больше нуля | `pydantic.ValidationError` — нулевой предел отбивал бы любой запрос с телом |
| `test_settings_missing_osrm_url` (параметризован: `OSRM_URL_CAR`, `OSRM_URL_FOOT`, `OSRM_URL_BIKE`) | одна из трёх переменных не задана | `pydantic.ValidationError` — у каждого профиля свой граф, запасного нет |
| `test_settings_osrm_defaults` | `PUBLIC_TRANSPORT_FACTOR`, `OSRM_MAX_TABLE_SIZE`, `OSRM_TIMEOUT_S` не заданы | `public_transport_factor == 1.5`, `osrm_max_table_size == 1000` (совпадает с `--max-table-size` стенда), `osrm_timeout_s == 60` |
| `test_settings_rejects_bad_osrm_timeout` (параметризован: `0`, `-1`, `inf`) | `OSRM_TIMEOUT_S` не положительное конечное число | `pydantic.ValidationError` |
| `test_settings_rejects_public_transport_factor_below_one` (параметризован: `0.9`, `0`, `-1`, `inf`, `nan`) | `PUBLIC_TRANSPORT_FACTOR` меньше 1 или не конечное число | `pydantic.ValidationError` — общественный транспорт не быстрее машины, а бесконечный коэффициент сделал бы матрицу бесконечной |
| `test_settings_rejects_non_positive_max_table_size` (параметризован: `0`, `-1`) | `OSRM_MAX_TABLE_SIZE` не больше нуля | `pydantic.ValidationError` |

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
| `test_configure_logging_silences_httpx_request_lines` | `configure_logging(settings)` с `log_level="DEBUG"`, запрос `httpx.AsyncClient` через `MockTransport` на URL с адресом в query и координатами в пути | в выводе нет строки `HTTP Request: …` и нет ни адреса, ни координат: URL внешних сервисов содержит персональные данные; `warning` и выше от `httpx` проходят |

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

## `alembic/versions/5d23f2956ce7_initial_schema.py` — схема БД

> Мока нет: `@pytest.mark.integration`, настоящий PostgreSQL 16 + PostGIS из
> `testcontainers` (образ `postgis/postgis:16-3.4`, тот же, что на стенде), один контейнер на
> весь прогон. Ревизия накатывается `alembic upgrade head` через `alembic/env.py` — тем же путём,
> что сервис `migrate` стенда; `MIGRATION_DATABASE_URL` указывает на владельца схемы в
> контейнере, `APP_RW_PASSWORD` и `APP_RO_PASSWORD` заданы. Проверки ролей подключаются
> под `app_rw` / `app_ro`, проверки ограничений — под `app_rw`, каждая в своей транзакции
> с откатом. Нарушение ограничения проверяется по имени ограничения в ошибке драйвера
> (`e.diag.constraint_name`), а не по тексту сообщения.

| Test | Scenario | Expected result |
|---|---|---|
| `test_upgrade_creates_schema` | `upgrade head` на пустой БД | таблицы `regions`, `engineers`, `tickets`, `plans`, `assignments`, `replan_events`; `alembic_version` = последняя ревизия `cb3db41d521a`; роли `app_rw` и `app_ro` существуют и могут входить |
| `test_downgrade_then_upgrade` | `downgrade base`, затем снова `upgrade head` | после отката шести таблиц и ролей нет, расширение `postgis` осталось; повторный накат проходит без ошибок |
| `test_upgrade_requires_role_passwords` | `APP_RW_PASSWORD` не задан; `upgrade head` | `RuntimeError` с именем переменной; таблиц и `alembic_version` в БД нет — транзакция ревизии откатилась целиком |
| `test_failed_ddl_rolls_back_whole_revision` | перед накатом в БД создана таблица `plans` (владельцем схемы); `upgrade head` | ошибка `DuplicateTable`; в БД нет ни одной из остальных пяти таблиц, ролей `app_rw`/`app_ro` и записи в `alembic_version` — ревизия откатилась целиком, схема осталась на прежней ревизии |
| `test_role_password_is_not_sql` | `APP_RW_PASSWORD` = `rw'pa ss; DROP TABLE x` | накат проходит; `app_rw` входит ровно с этим паролем |
| `test_existing_role_is_reset` | до наката в кластере уже есть роль `app_rw` с `CREATEROLE`, `CREATEDB` и другим паролем | после наката у `app_rw` нет ни `SUPERUSER`, ни `CREATEROLE`, ни `CREATEDB`, ни `REPLICATION`, ни `BYPASSRLS`; вход — только с паролем из `APP_RW_PASSWORD` |
| `test_app_rw_changes_data` | под `app_rw`: `INSERT`, `UPDATE`, `DELETE` строки `regions`, `SELECT` | все операции проходят; `id` выдаёт `IDENTITY` без отдельного права на последовательность |
| `test_app_rw_cannot_change_schema` | под `app_rw`: `CREATE TABLE x (id int)`; `ALTER TABLE tickets ADD COLUMN y int`; `DROP TABLE plans` | каждая — `InsufficientPrivilege` |
| `test_app_ro_is_read_only` | под `app_ro`: `SELECT` из каждой таблицы; `INSERT` в `regions` | `SELECT` проходит; `INSERT` — `InsufficientPrivilege` |
| `test_timestamps_are_naive_without_default` | каталог: все колонки с временем (`tickets.window_start`, `window_end`, `received_at`, `plans.created_at`, `assignments.planned_arrival`, `replan_events.triggered_at`) | тип каждой — `timestamp without time zone` с точностью до секунды (`datetime_precision = 0`), `column_default` пуст; колонок `… with time zone` (ни `timestamptz`, ни `timetz`) в схеме нет |
| `test_timestamp_keeps_whole_seconds` | `received_at = 2026-09-22 18:00:05.7` | прочитано `2026-09-22 18:00:06` — долей секунды, которых не принимает контракт, в БД нет |
| `test_naive_time_roundtrips_unchanged` | сессия `SET TIME ZONE 'America/New_York'`; вставка заявки с `window_start = 2026-09-23 13:20:00`; чтение из сессии с `TIME ZONE 'UTC'` | прочитано `datetime(2026, 9, 23, 13, 20)` без `tzinfo` — значение не пересчитано ни при записи, ни при чтении |
| `test_engineer_skills_valid` | навыки `['emergency']`, `['local_work', 'connection', 'emergency']` | строка вставлена |
| `test_engineer_skills_rejected` | навыки `[]`; 4 значения; `['cooking']`; `['local_work', NULL]`; двумерный массив `{{local_work},{connection}}` | каждый случай — `CheckViolation`, ограничение `ck_engineers__skills` |
| `test_engineer_shift_order` | `shift_start = 18:00`, `shift_end = 09:00` | `CheckViolation`, `ck_engineers__shift_order` |
| `test_engineer_vehicle_type` | `vehicle_type = 'truck'` | `CheckViolation`, `ck_engineers__vehicle_type` |
| `test_ticket_window_order` | `window_start = window_end`; `window_start` позже `window_end` | оба — `CheckViolation`, `ck_tickets__window_order` |
| `test_ticket_closed_sets` | по одному недопустимому значению в `required_skill`, `required_vehicle`, `status`; `priority = 0`; `duration_min = 0` | `CheckViolation` с именем своего ограничения (`ck_tickets__required_skill`, `…__required_vehicle`, `…__status`, `…__priority_rank`, `…__duration_positive`) |
| `test_ticket_priority_rank` | `priority` = 1, 2, 3 и 7 | строка вставлена: ранг — любое целое от 1, новый уровень приоритета не требует изменения схемы |
| `test_ticket_vehicle_may_be_absent` | `required_vehicle = NULL` | строка вставлена: заявка без требования к транспорту допустима |
| `test_ticket_requires_location` | `geom = NULL` | `NotNullViolation` |
| `test_assignment_shapes_valid` | назначенная строка (бригада, номер, прибытие, путь, без причины); неназначенная (только `unassigned_reason` и `explanation`) | обе вставлены |
| `test_assignment_shapes_rejected` | назначенная без `travel_time_min`; назначенная с `unassigned_reason`; неназначенная с `engineer_id`; строка без бригады и без причины | каждая — `CheckViolation`, `ck_assignments__assigned_or_reason` |
| `test_assignment_ticket_once_per_plan` | та же заявка второй раз в том же плане | `UniqueViolation`, `ux_assignments__plan_id_ticket_id`; в другом плане — вставляется |
| `test_assignment_sequence_unique_per_engineer` | два визита одной бригады с одним `sequence_no` в плане; `sequence_no = 0` | `UniqueViolation` `ux_assignments__plan_id_engineer_id_sequence_no`; `CheckViolation` `ck_assignments__sequence_no_positive` |
| `test_assignment_arrival_whole_minute` | назначенная строка с `planned_arrival = 2026-09-23 10:30:15` | `CheckViolation`, `ck_assignments__planned_arrival_whole_minute` — расписание хранится с точностью до минуты |
| `test_assignment_reason_set` | `unassigned_reason = 'busy'` | `CheckViolation`, `ck_assignments__unassigned_reason` |
| `test_replan_event_types` | `event_type` каждого из `new_urgent_ticket`, `new_ticket`, `ticket_cancelled`, `engineer_unavailable`; затем `'reorder'` | четыре вставлены; последнее — `CheckViolation`, `ck_replan_events__event_type` |
| `test_foreign_keys_enforced` | `engineers.region_id`, `plans.parent_plan_id`, `assignments.ticket_id` на несуществующий `id` | каждая — `ForeignKeyViolation` |
| `test_every_foreign_key_is_indexed` | каталог: колонки всех внешних ключей | каждая — первая колонка какого-либо индекса или уникального ограничения |
| `test_every_table_and_column_is_commented` | каталог: `obj_description` таблиц и `col_description` колонок, кроме `id` | ни одного пустого комментария |

## `alembic/versions/cb3db41d521a_tickets_type_hd_not_null.py` — тип заявки HD обязателен

Файл: `tests/db/test_schema.py`.

> Мока нет: `@pytest.mark.integration`, контейнер PostGIS, окружение и роли — как в разделе
> схемы БД. Состояние до ревизии — `upgrade 5d23f2956ce7`.

| Test | Scenario | Expected result |
|---|---|---|
| `test_ticket_type_hd_required` | под `app_rw` вставка заявки с `type_hd = NULL` | `NotNullViolation`, колонка `type_hd` (`e.diag.column_name`) |
| `test_type_hd_upgrade_keeps_tickets` | на ревизии `5d23f2956ce7` есть заявка с `type_hd`; `upgrade head` | заявка на месте без изменений; комментарий колонки говорит, что тип обязателен |
| `test_type_hd_upgrade_fails_on_null` | на ревизии `5d23f2956ce7` владельцем схемы вставлена заявка с `type_hd = NULL`; `upgrade head` | `NotNullViolation`; `alembic_version` = `5d23f2956ce7`, заявка не изменена — пустой тип не заполняется выдуманным значением |
| `test_type_hd_downgrade` | `downgrade 5d23f2956ce7`, вставка заявки с `type_hd = NULL`, удаление её, `upgrade head` | после отката `NULL` принимается, прежний комментарий колонки; повторный накат проходит |

## `alembic/versions/c124884e0c63_plans_status.py` — статус построения плана

Файл: `tests/db/test_schema.py`.

> Мока нет: `@pytest.mark.integration`, контейнер PostGIS, окружение и роли — как в разделе
> схемы БД. Состояние до ревизии — `upgrade cb3db41d521a`.

| Test | Scenario | Expected result |
|---|---|---|
| `test_plan_status_valid` (`running`/`done`/`failed`) | вставка плана с этим `status` (`failed` — с `failed_reason`) | принято |
| `test_plan_status_closed_set` | `status = 'queued'` | `CheckViolation`, `ck_plans__status` |
| `test_plan_failed_reason_closed_set` | `status = 'failed', failed_reason = 'timeout'` | `CheckViolation`, `ck_plans__failed_reason` |
| `test_plan_status_failed_reason_shape` (`failed` без причины / `done` или `running` с причиной) | несогласованная пара `status`/`failed_reason` | `CheckViolation`, `ck_plans__status_failed_reason` |

## `alembic/env.py` — запуск миграций

> Мока нет: `@pytest.mark.integration`, контейнер PostGIS как в предыдущем разделе.
> Команда запускается отдельным процессом (`python -m alembic upgrade head` из `back/`) с
> явно собранным окружением — так же, как её запускает сервис `migrate` стенда.

| Test | Scenario | Expected result |
|---|---|---|
| `test_env_uses_migration_url` | в окружении `MIGRATION_DATABASE_URL` на контейнер, `DATABASE_URL` нет, `sqlalchemy.url` в `alembic.ini` пуст | код `0`, ревизия применена |
| `test_env_accepts_plain_postgresql_url` | `MIGRATION_DATABASE_URL` в виде `postgresql://…` (как на стенде, без имени драйвера) | код `0`: драйвер `psycopg` подставляет сам `env.py` |
| `test_env_logs_are_json` | `LOG_FORMAT=json`; `upgrade head` на пустой БД | каждая строка вывода — один JSON-объект; есть записи о применении ревизий `5d23f2956ce7` и `cb3db41d521a`; паролей ролей и адреса БД с паролем в выводе нет |
| `test_env_failure_exits_nonzero` | `MIGRATION_DATABASE_URL` на порт, где никто не слушает | код `≠ 0`, последняя запись вывода — JSON уровня `error` об ошибке подключения; паролей ролей и владельца в выводе нет — параметры упавших операторов в текст ошибки не попадают |
| `test_env_refuses_offline_mode` | `alembic upgrade head --sql` | код `≠ 0`; последняя запись — JSON `migration_failed` с причиной «offline mode is not supported»: пароли ролей не попадают в сгенерированный SQL |

## `src/repository/db.py` — обёртка запросов к БД

> Замена стабами: вместо метода aiosql — асинхронная функция, которая возвращает значение или
> поднимает заданное исключение драйвера (`psycopg.errors.*`, `psycopg_pool.PoolTimeout`).
> БД не нужна: проверяется только превращение ошибки драйвера в запись лога и доменное
> исключение. Логи — разбором JSON-строк stderr (`capsys`): логгер модуля кэширует
> конфигурацию при первом использовании, и `capture_logs()` его запись не видит.

| Test | Scenario | Expected result |
|---|---|---|
| `test_run_returns_result` | функция возвращает `[{"id": 1}]` | возвращено то же значение; записей лога нет |
| `test_run_connection_error_is_dependency_unavailable` | функция поднимает `psycopg.OperationalError` (`sqlstate = "08006"`) | запись `db_query_failed` уровня `error` с `query` (имя запроса) и `sqlstate = "08006"`; поднято `DependencyUnavailable(reason="db_unavailable")`, `__cause__` — исходная ошибка; на HTTP это `503` без тела |
| `test_run_pool_timeout_is_dependency_unavailable` | функция поднимает `PoolTimeout` (нет свободного соединения) | `db_query_failed` с `sqlstate = None`; `DependencyUnavailable(reason="db_unavailable")` |
| `test_run_other_db_error_is_database_failure` | функция поднимает `psycopg.errors.UniqueViolation` | `db_query_failed` с `sqlstate = "23505"`; поднято `DatabaseFailure(reason="db_query_failed")`, `__cause__` — исходная ошибка; повтор не поможет — на HTTP это `500` без тела, обработчик второй записи не пишет |
| `test_run_logs_no_parameters` | функция вызвана с адресом заявки в параметрах и падает с `OperationalError` | в записи `db_query_failed` только `query`, `sqlstate` и уровень — ни значений параметров, ни текста SQL |

## `src/repository/region_data.py` — замена данных региона

Файл: `tests/repository/test_region_data.py`.

> Мока нет: `@pytest.mark.integration`, контейнер PostGIS и ревизия, как в разделе схемы БД;
> запросы из `queries/*.sql` вызываются через aiosql под ролью `app_rw`. Нарушение ограничения
> проверяется по имени ограничения в исходной ошибке драйвера (`__cause__`).

| Test | Scenario | Expected result |
|---|---|---|
| `test_replace_inserts_region_engineers_tickets` | пустая БД; регион `east`, 2 бригады, 3 заявки | возвращены `id` региона и `engineers_kept = false`; в БД 1 регион, 2 бригады и 3 заявки этого региона; точки, смены, навыки, окна и `received_at` прочитаны обратно без изменений (время — наивное, как передано) |
| `test_replace_same_code_keeps_region_id` | регион `east` загружен дважды с разным названием и офисом | тот же `id`; название, адрес и точка офиса — из второй загрузки |
| `test_replace_removes_previous_region_data` | у региона есть бригады, заявки, два плана (второй — потомок первого), строки плана и событие перепланирования; загрузка нового набора с другим составом бригад (другие названия) | прежних бригад, заявок, планов, строк планов и событий региона нет; бригады и заявки — из нового набора |
| `test_replace_same_roster_keeps_engineers` | у региона есть 2 бригады, заявки и план с назначением бригаде; повторная загрузка с теми же бригадами (названия, навыки, транспорт, смены), другими точками старта и новыми заявками | `engineers_kept = true`; `id` бригад прежние; точки старта — из второй загрузки; остальные поля бригад прежние; заявки — из второй загрузки; планов, строк планов и событий региона нет |
| `test_replace_changed_roster_recreates_engineers` | у региона 2 бригады; повторная загрузка с 3 бригадами | `engineers_kept = false`; у региона 3 бригады из второй загрузки; прежних `id` бригад нет |
| `test_replace_skills_order_keeps_engineers` | повторная загрузка той же бригады с навыками в другом порядке | `engineers_kept = true`, `id` бригады прежний: порядок навыков на сравнение состава не влияет |
| `test_replace_changed_brigade_recreates_engineers` (параметризован: навыки, транспорт, начало смены, конец смены второй бригады) | у региона 2 бригады; повторная загрузка с теми же названиями, у второй бригады изменено одно поле | `engineers_kept = false`, бригады созданы заново: прежних `id` нет — состав сравнивается по всем полям генератора, а не только по названиям |
| `test_replace_keeps_other_regions` | загружены `east` и `south_east`, затем `east` загружен повторно | данные `south_east` не изменились |
| `test_replace_duplicate_external_id_loads_both` | две заявки с одинаковым `external_id` | обе вставлены, у каждой свой `id` |
| `test_replace_constraint_violation_rolls_back` | у региона уже есть данные; новый набор содержит бригаду с 4 навыками | поднято `DatabaseFailure(reason="db_query_failed")`, причина — нарушение `ck_engineers__skills`; запись `db_query_failed`; прежние данные региона на месте, новых нет |
| `test_replace_overnight_shift_rolls_back` | бригада со сменой `22:00–06:00` | `DatabaseFailure`, нарушение `ck_engineers__shift_order`; прежние данные на месте |

## `src/repository/region_lists.py` — чтение бригад и заявок региона

Файл: `tests/repository/test_region_lists.py`.

> Мока нет: `@pytest.mark.integration`, контейнер PostGIS и ревизия, как в разделе схемы БД;
> данные регионов записываются `replace_region_data`, чтение — запросами из `queries/*.sql`
> через aiosql под ролью `app_rw`.

| Test | Scenario | Expected result |
|---|---|---|
| `test_get_region_id` | загружен регион `east`; коды `east` и `south_east` (не загружен) | для `east` — его `id`; для `south_east` — `None` |
| `test_list_engineers_of_region` | загружены `east` (2 бригады) и `south_east` (1 бригада) | для `east` — ровно его 2 бригады по возрастанию `id`; у бригады `start` — `Point` с переданными широтой и долготой (не переставлены), навыки — кортеж `Skill`, транспорт — `VehicleType`, смены — `time`, как переданы |
| `test_list_tickets_of_region` | загружены `east` (3 заявки) и `south_east` (1 заявка) | для `east` — ровно его 3 заявки по возрастанию `id`; `location` — `Point` с переданными координатами; окна и `received_at` — наивные `datetime`, равные переданным; `type_bk`, `district`, `required_vehicle`, не заданные у заявки, — `None` |
| `test_lists_of_region_without_rows` | `id`, под которым в БД нет ни бригад, ни заявок | оба списка пустые |
| `test_lists_db_unavailable` | соединение закрыто до вызова | `DependencyUnavailable(reason="db_unavailable")`; запись `db_query_failed` с именем запроса |

## `src/repository/tickets.py` — статус заявки

Файл: `tests/repository/test_tickets.py`.

> Мока нет: `@pytest.mark.integration`, контейнер PostGIS и ревизия, как в разделе схемы БД;
> заявки записываются `replace_region_data`, запросы `lock_ticket` и `update_ticket_status`
> из `queries/tickets.sql` вызываются через aiosql под ролью `app_rw`. Нарушение ограничения
> проверяется по имени ограничения в исходной ошибке драйвера (`__cause__`).

| Test | Scenario | Expected result |
|---|---|---|
| `test_lock_ticket` | загружен регион с заявкой; `lock_ticket` по её `id` в транзакции | `Ticket` с теми же полями, что у этой заявки в `list_tickets` (координаты не переставлены, окна — наивные `datetime`) |
| `test_lock_ticket_missing` | `id`, которого нет в таблице | `None` |
| `test_update_ticket_status` | `update_ticket_status(id, completed, cancelled_after_dispatch=False)` | возвращён `Ticket` со статусом `completed`, остальные поля без изменений; `list_tickets` видит `completed`; `cancelled_after_dispatch` в строке — `false`; другие заявки региона не изменились |
| `test_update_ticket_status_cancelled_after_dispatch` | `update_ticket_status(id, cancelled, cancelled_after_dispatch=True)` | в строке `status = 'cancelled'`, `cancelled_after_dispatch = true` |
| `test_update_ticket_status_check_constraint` | статус `'bogus'` в обход домена | `DatabaseFailure(reason="db_query_failed")`, причина — нарушение `ck_tickets__status`; строка не изменилась |
| `test_lock_ticket_waits_for_concurrent_change` | соединение A в транзакции взяло `lock_ticket` и записало `en_route`; соединение B вызывает `lock_ticket` той же заявки | B не получает строку, пока A не зафиксировал транзакцию (за 0,3 с ожидания результата нет); после COMMIT у A — B получает заявку со статусом `en_route` |
| `test_ticket_queries_db_unavailable` (параметризован: `lock_ticket`, `update_ticket_status`) | соединение закрыто до вызова | `DependencyUnavailable(reason="db_unavailable")`; запись `db_query_failed` с именем запроса |

## `src/service/ticket_file.py` — чтение файла заявок

Файл: `tests/service/test_ticket_file.py`.

> Мок не нужен: чистые функции над байтами и строками. Таблица типов — из тестовой копии
> конфигурации, а не из `data/`.

### Кодировка

| Test | Scenario | Expected result |
|---|---|---|
| `test_csv_utf8` | CSV в UTF-8 без BOM, строка с кириллицей и служебная строка | строки и адрес офиса разобраны, кириллица без искажений |
| `test_csv_utf8_bom` | тот же CSV в UTF-8 с BOM | результат совпадает с `test_csv_utf8`; первая колонка называется `Заявка`, а не `﻿Заявка` |
| `test_csv_cp1251` | тот же CSV в cp1251 без BOM | результат совпадает с `test_csv_utf8` |
| `test_csv_cp1251_after_utf8_bom` | байты UTF-8 BOM, за ними CSV в cp1251 | BOM отброшен, файл прочитан как cp1251; результат совпадает с `test_csv_utf8` |
| `test_csv_source_files_read` | исходные файлы `docs/synthetic_data/*.csv` как есть (cp1251) | 66, 83 и 56 заявок; адрес офиса найден в каждом |
| `test_csv_undecodable_rejected` | байты, не являющиеся ни UTF-8, ни cp1251 (`0x98` вне UTF-8-последовательности) | `InvalidInput(reason="file_encoding_invalid")` с `message` о формате файла |
| `test_json_utf8_with_and_without_bom` | JSON-массив тех же заявок в UTF-8 без BOM и с BOM | результат совпадает с `test_csv_utf8` |
| `test_json_cp1251_rejected` | тот же JSON в cp1251 | `InvalidInput(reason="file_encoding_invalid")` |

### Формат и служебные строки

| Test | Scenario | Expected result |
|---|---|---|
| `test_csv_columns_by_header` | колонки в другом порядке и без необязательной колонки `Подключение` (как в файлах контрольного распределения) | поля разобраны по заголовку |
| `test_csv_missing_required_column` | в заголовке нет `Адрес` | `InvalidInput(reason="file_format_invalid")`, `message` называет недостающую колонку |
| `test_json_not_array_of_objects` | JSON — объект, число, массив строк | `InvalidInput(reason="file_format_invalid")` |
| `test_json_invalid_syntax` | обрезанный JSON; пустой файл | `InvalidInput(reason="file_format_invalid")` |
| `test_json_malformed_array` | данные после `]`; элементы без запятой; висящая запятая; `[,]` | `InvalidInput(reason="file_format_invalid")` |
| `test_json_whitespace_around_elements` | пробелы, переводы строк и табуляция вокруг скобок, запятых и элементов; пустой массив в пробелах | разобраны оба элемента: заявка и пустой объект (пропущен как пустая строка); пустой массив — ноль строк |
| `test_unparsable_file_is_format_error` | поле CSV длиннее предела библиотеки `csv` (200 000 символов); JSON из 200 000 `[`; JSON с числом из 5000 цифр | `InvalidInput(reason="file_format_invalid")`, а не необработанное исключение (`500`) |
| `test_json_bad_value_in_known_column` | в JSON значение «Адрес» — вложенный объект | `InvalidInput(reason="file_format_invalid")`, `message` называет колонку |
| `test_unknown_columns_dropped` | JSON с ключом из 1000 символов (вложенный объект) и `Бригада`; CSV с колонками `Подключение` и `Бригада` | в строке только колонки, которые использует загрузчик; неизвестный ключ с вложенным объектом не ошибка |
| `test_too_many_columns` | заголовок CSV из 20 005 колонок и 1000 пустых строк | `InvalidInput(reason="file_format_invalid")` быстрее 100 мс |
| `test_too_many_rows` | CSV и JSON из 501 заявки; CSV из 500 заявок, пустой строки, строки из одних разделителей и строки адреса офиса | `InvalidInput(reason="too_many_rows")` для 501; 500 заявок — файл принят, после отбрасывания служебных строк остаются 500 заявок |
| `test_blank_rows_are_counted_not_kept` | CSV из заявки и 200 000 пустых строк | одна заявка, `skipped = 200 000`; пик памяти разбора меньше 20 МБ — пустые строки только считаются (сохранённая строка стоила бы ~400 байт, всего ~80 МБ) |
| `test_blank_rows_skipped` | между заявками — две пустые строки, строка из одних `;`, строка из пробелов и табуляции, строка, где заполнена только неизвестная колонка | не заявки, `rows_skipped = 5`, в `rows_invalid` не попали |
| `test_sentinel_row_gives_office_address` | служебная строка `Адрес Офиса` и, в другом файле, `Адрес офиса` | обе отброшены до проверки полей, в `rows_skipped`; адрес офиса — значение второго столбца |
| `test_no_sentinel_row` | файл без служебной строки | адреса офиса нет (`None`), заявки разобраны |

### Строка-заявка

| Test | Scenario | Expected result |
|---|---|---|
| `test_row_parsed` | валидная строка подключения | заявка: номер, типы BK/HD как есть, навык `connection`, ранг 2, 70 мин, район, адрес, окно `2026-08-17 10:00–12:00` без часового пояса |
| `test_row_single_digit_hour` | окно `17.08.2026 0:01` – `17.08.2026 23:59` | окно `00:01–23:59` |
| `test_row_missing_required_field` | пусто одно из полей `Заявка`, `Тип заявки HD`, `Начало`, `Окончание`, `Адрес` (параметризовано) | строка невалидна: номер строки файла и причина `missing_field` с именем колонки |
| `test_row_bad_datetime` | `2026-08-17 10:00`, `17.08.2026`, `32.08.2026 10:00` | невалидна, причина `bad_datetime` |
| `test_row_window_not_ordered` | начало окна равно окончанию и позже окончания | невалидна, причина `window_order` |
| `test_row_unknown_type` | `Тип заявки HD` нет в таблице соответствия | невалидна, причина `unknown_type` |
| `test_row_status_from_column` | колонка `Статус BK` со значением каждого из семи статусов словаря данных | статус `not_sent` … `overdue` по таблице |
| `test_row_status_default_sent` | колонки `Статус BK` нет | статус `sent` |
| `test_row_unknown_status` | `Статус BK` = `Неизвестно` | невалидна, причина `unknown_status` |
| `test_row_received_at_start_of_day` | окно `17.08.2026 20:00–22:00` | `received_at = 2026-08-17 00:00:00`, без часового пояса |
| `test_field_too_long` | адрес из 317 символов; район из 201 символа | невалидна, причина `field_too_long` с именем колонки |
| `test_invalid_row_does_not_stop_others` | 3 строки, вторая невалидна | 2 заявки, 1 невалидная строка с номером 3 (строка заголовка — 1) |

## `src/service/ticket_types.py` — таблица соответствия типов заявок

Файл: `tests/service/test_ticket_types.py`.

> Мок не нужен: чтение конфигурации из временного файла и чистая функция классификации.

| Test | Scenario | Expected result |
|---|---|---|
| `test_emergency_by_hd_whatever_bk` | HD = `Авария` при BK = `Глобальная проблема`, `Подключение`, `Локальная заявка`, пустом BK (параметризовано) | навык `emergency`, ранг 1, 80 мин |
| `test_global_problem_without_emergency` | BK = `Глобальная проблема`, HD = `Информация` | `local_work`, ранг 3, 30 мин |
| `test_connection_and_reorder_priorities` | BK = `Подключение` и BK = `Дозаказ` с HD = `Заказ подключения/Дозаказ оборудования` | оба `connection`; ранг 2 и 70 мин у подключения, ранг 3 и 20 мин у дозаказа |
| `test_tv_and_tve_are_separate_values` | HD = `ТВ. Замена приставки техником` и `TVE/ENT. Замена приставки техником` | обе строки таблицы найдены, `local_work` |
| `test_every_source_type_mapped` | все пары BK/HD из исходных файлов `docs/synthetic_data` и `docs/control_distribution` | ни одной пары без соответствия |
| `test_unknown_hd` | HD, которого нет в таблице | `None` |
| `test_config_from_file` | конфигурация с новым типом работ и новым рангом 4 | новый тип классифицируется с рангом 4 без изменений кода |
| `test_config_invalid_rejected` | в конфигурации навык не из трёх допустимых, ранг 0, длительность 0 (параметризовано) | ошибка при чтении конфигурации с именем ключа |

## `src/service/regions.py` — конфигурация регионов

Файл: `tests/service/test_regions.py`.

> Мок не нужен: чтение конфигурации из временного файла.

| Test | Scenario | Expected result |
|---|---|---|
| `test_regions_config_shipped` | `data/regions.toml` из репозитория | три региона `east`, `south_east`, `south_center`: название, центр, число бригад 13, 12, 11, три вида смен |
| `test_unknown_region_code` | код `north` | `InvalidInput(reason="unknown_region")` с полем `region` |
| `test_overnight_shift_rejected` | смена `22:00–06:00` и смена с началом, равным концу | ошибка при чтении конфигурации |
| `test_too_many_engineers_rejected` | 31 бригада у региона; 30 бригад | 31 — ошибка при чтении конфигурации; 30 — конфигурация читается |
| `test_too_few_full_day_engineers_rejected` | 5 бригад при долях 25 % / 25 % (на весь день остаётся 3) | ошибка при чтении: бригад «весь день» меньше четырёх |

## `src/service/engineers_generator.py` — генератор демо-бригад

Файл: `tests/service/test_engineers_generator.py`.

> Мок не нужен: генератор — чистая функция от конфигурации региона, точки офиса и районов
> заявок.

| Test | Scenario | Expected result |
|---|---|---|
| `test_count_from_region_config` | регион с 13 бригадами | 13 бригад |
| `test_skills_one_to_three` | каждый регион из конфигурации | у каждой бригады от 1 до 3 различных навыков из `local_work`, `connection`, `emergency` |
| `test_all_skills_and_vehicles_present` | каждый регион | в наборе есть все три навыка и все четыре типа транспорта |
| `test_shift_kinds_split` | 13 бригад, доли 25 % / 25 % | 3 утренние `10:00–18:00`, 3 вечерние `15:30–23:30`, 7 на весь день `10:00–23:30` |
| `test_full_day_covers_skills_and_vehicles` | каждый регион | бригады «весь день» вместе имеют все три навыка и все четыре типа транспорта |
| `test_shifts_within_one_day` | каждый регион | у каждой бригады начало смены раньше конца, конец не позже `23:59` |
| `test_deterministic` | два вызова с одинаковым входом | одинаковые бригады: имена, навыки, транспорт, смены, точки |
| `test_start_at_office` | районы заявок только московские | все бригады стартуют из точки офиса |
| `test_remote_town_start` | среди районов заявок `Домодедово` и `Ступино` | по одной бригаде «весь день» стартует из точки каждого из этих городов, остальные — из офиса |
| `test_names_without_personal_data` | каждый регион | имя бригады — «Бригада N», без фамилий |

## `src/service/geocoding.py` — координаты адресов

Файл: `tests/service/test_geocoding.py`.

> Замена стабами: клиент Nominatim — фейк, который возвращает заданную точку или `None`,
> поднимает `DependencyUnavailable` и запоминает запросы. Гео-кэш — в памяти, точки удалённых
> городов — тестовые. Логи — JSON-строки stderr, как в разделе загрузчика.

| Test | Scenario | Expected result |
|---|---|---|
| `test_remote_town_from_config` | адрес в Домодедово (по району и по названию в адресе) | точка Домодедово из конфигурации регионов; клиент не вызван; не считается промахом кэша |
| `test_query_from_address` | `Город Москва, пр-кт.Волгоградский, д. 128 к 5, кв. 12`; `д 83с 4`; `д. 24/30 стр. 1`; `Бирюлевская ул. д. 44` | первый запрос: `Волгоградский проспект 128к5, Москва`, `… 83с4`, `… 24/30с1`, `Бирюлевская улица 44, Москва`; квартира отброшена |
| `test_query_variants` | `ул.2-я Синичкина, д. 9 к 1` | запросы по очереди: название до типа, тип до названия, `2-я улица Синичкина 9к1`, дом без корпуса `9` |
| `test_apartment_anywhere_dropped` | квартира и подъезд в конце, в середине, «квартира 12 (домофон 12К)», слитно «д.5кв.12» | первый запрос `Подольская улица 5, Москва`; ни в одном запросе нет номера квартиры и подъезда |
| `test_query_linear_time` | адрес из 100 000 пробелов, из 50 000 слов, из 30 000 повторов «д1» | каждый разобран быстрее 0,5 с (квадратичный разбор такой строки занимает минуты) |
| `test_hyphenated_word_is_not_apartment` | «Под-ский пр-кт., д. 7»; «кв-л 137а» | улица и квартал остаются в запросе |
| `test_cache_hit_no_request` | все адреса есть в кэше | точки из кэша; клиент не вызван; записи `geocode_cache_miss` нет |
| `test_cache_key_normalized` | адрес отличается от записи кэша регистром и лишними пробелами | найден в кэше |
| `test_miss_goes_to_nominatim` | 2 адреса из 5 не в кэше | клиент вызван для этих 2 (первый вариант запроса найден); запись `geocode_cache_miss` с `misses = 2`, `lookups_skipped = 0` и без адресов |
| `test_lookups_capped` | 5 промахов при пределе 2 | запросы только по первым 2 адресам; `geocode_cache_miss` с `misses = 5`, `lookups_skipped = 3` |
| `test_miss_not_found` | клиент вернул `None` на все варианты запроса | адрес без точки, остальные с точками |
| `test_repeated_miss_requested_once` | один и тот же адрес-промах у трёх заявок | один вызов клиента |
| `test_nominatim_disabled` | клиента нет (адрес Nominatim не задан), 2 промаха | адреса-промахи без точки; сетевых вызовов нет |
| `test_nominatim_unavailable` | клиент поднимает `DependencyUnavailable` | то же исключение пробрасывается |
| `test_geocache_covers_every_source_address` | гео-кэш `data/geocache.csv` и точки удалённых городов из репозитория; все адреса и адреса офиса из `docs/synthetic_data` и `docs/control_distribution`; клиента нет | у каждого адреса есть точка; сети нет |

## `src/service/loader.py` — загрузка данных региона

Файл: `tests/service/test_loader.py`.

> Замена стабами: репозиторий (`replace_region_data` — фейк, который запоминает переданные
> регион, бригады и заявки или поднимает заданное исключение), фабрика соединений — фейк,
> который считает взятые соединения, клиент Nominatim — фейк, как
> в предыдущем разделе. Гео-кэш и конфигурации — тестовые файлы; разбор файла, генератор
> бригад и геокодирование — настоящие. Логи — разбором JSON-строк stderr (`capsys`,
> `tests/log_records.py`): логгеры модулей кэшируют конфигурацию при первом использовании, и
> `capture_logs()` не видит логгер, уже использованный другим тестом.

| Test | Scenario | Expected result |
|---|---|---|
| `test_load_csv` | CSV региона `east`: 3 заявки, 2 пустые строки, служебная строка, 1 невалидная строка | в репозиторий переданы регион `east` с офисом из служебной строки, бригады генератора и 3 заявки; итог: `rows_total = 7`, `rows_skipped = 3`, `rows_invalid = 1` с номером строки и причиной; запись `data_load_finished` с `source = csv`, `region`, `rows_total`, `rows_skipped`, `rows_invalid`, `invalid_by_reason = {"bad_datetime": 1}`, `engineers`, `engineers_kept` (как вернул репозиторий), `tickets`, `duration_ms`, `wait_ms` не больше `duration_ms` |
| `test_load_json` | тот же набор в JSON | тот же итог, `source = json` |
| `test_load_demo` | демо-набор `south_east` | заявки из `data/demo/south_east.csv`: 83 заявки, `rows_invalid = 0`, `source = demo` |
| `test_load_demo_offline` | демо-набор каждого региона, гео-кэш из репозитория, клиента Nominatim нет | все заявки загружены, `rows_invalid = 0`; сетевых вызовов нет |
| `test_office_without_sentinel_is_region_center` | файл без служебной строки | офис — центр региона из конфигурации, адрес офиса — название региона |
| `test_office_not_geocoded_is_region_center` | адрес офиса не найден | точка офиса — центр региона |
| `test_ticket_without_point_is_invalid` | адрес заявки не найден ни в кэше, ни клиентом | заявка не передана в репозиторий; `rows_invalid` содержит её строку с причиной `address_not_found`; в `data_load_finished` `invalid_by_reason = {"bad_datetime": 1, "address_not_found": 1}` |
| `test_no_valid_tickets` | все строки невалидны или файл содержит только служебную строку | `InvalidInput(reason="no_valid_tickets")` с `message`; репозиторий не вызван; запись `data_load_failed` с `reason`, `rows_total`, `rows_invalid`, `duration_ms` |
| `test_encoding_error_logged` | неподдерживаемая кодировка | `InvalidInput(reason="file_encoding_invalid")`; запись `data_load_failed` с `reason`, `source`, `region`; репозиторий не вызван |
| `test_geocoder_unavailable` | клиент Nominatim поднимает `DependencyUnavailable` | то же исключение, `reason = "geocoder_unavailable"`; репозиторий не вызван; запись `data_load_failed` |
| `test_repository_failure` | репозиторий поднимает `DependencyUnavailable` и `DatabaseFailure` (параметризовано) | исключение пробрасывается без изменений; запись `data_load_failed` с его `reason` |
| `test_connection_taken_only_to_write` | успешная загрузка; загрузка, прерванная недоступным Nominatim | соединение взято один раз — на запись; при отказе геокодера не взято ни одного |
| `test_client_error_logged_as_warning` | неподдерживаемая кодировка; отказ БД | `data_load_failed` на уровне `warning` и `error` соответственно |
| `test_unknown_region_logged` | код региона `north` | `InvalidInput(reason="unknown_region")`; репозиторий не вызван; `data_load_failed` с `reason`, `region = north`, уровень `warning` |
| `test_too_many_rows` | CSV из 501 заявки | `InvalidInput(reason="too_many_rows")`; репозиторий не вызван |
| `test_pool_timeout_is_dependency_unavailable` | фабрика соединений поднимает `PoolTimeout` | `DependencyUnavailable(reason="db_unavailable")`; репозиторий не вызван; записи `db_query_failed` (`query = replace_region_data`) и `data_load_failed` уровня `error` |
| `test_unknown_region_code_bounded_in_log` | код региона из 5000 символов с переводом строки | в записи `data_load_failed` поле `region` — 50 символов |
| `test_logs_no_addresses` | загрузка с промахами кэша и невалидными строками | ни в одной записи лога нет адресов и текста строк файла — только счётчики и коды причин |
| `test_files_read_one_at_a_time` | три загрузки запущены одновременно; разбор файла в подклассе загрузчика занимает время в своём потоке | все три завершились; одновременно разбирался не больше одного файла |
| `test_writes_one_at_a_time` | три загрузки запущены одновременно; фейковый репозиторий отдаёт управление event loop внутри записи | все три записаны; одновременно шла не больше одной записи — загрузки занимают не больше одного соединения пула; последняя в очереди загрузка пишет в `data_load_finished` `wait_ms` не меньше 15 мс (ждала две записи по 20 мс) |

## `src/service/region_lists.py` — регионы, бригады и заявки региона

Файл: `tests/service/test_region_lists.py`.

> Замена стабами: репозиторий (`get_region_id`, `list_engineers`, `list_tickets` — фейки,
> которые возвращают заданное значение, поднимают заданное исключение и запоминают вызовы),
> фабрика соединений — фейк, который считает взятые соединения. Конфигурация регионов —
> `data/regions.toml` из репозитория.

| Test | Scenario | Expected result |
|---|---|---|
| `test_regions_in_config_order` | конфигурация с регионами `east`, `south_east`, `south_center` | пары (код, название) в порядке конфигурации; соединение не взято |
| `test_engineers_of_loaded_region` | `get_region_id` вернул `7`, `list_engineers` — 2 бригады | эти 2 бригады без изменений; `list_engineers` вызван с `region_id = 7` |
| `test_tickets_of_loaded_region` | `get_region_id` вернул `7`, `list_tickets` — 3 заявки | эти 3 заявки без изменений; `list_tickets` вызван с `region_id = 7` |
| `test_region_not_loaded_is_empty` | регион из конфигурации, `get_region_id` вернул `None` | пустой список бригад и заявок; `list_engineers` и `list_tickets` не вызваны |
| `test_unknown_region` | код `north` | `InvalidInput(reason="unknown_region")` с `fields = [("region", "Неизвестный регион")]`; соединение не взято |
| `test_repository_failure_propagates` | репозиторий поднимает `DependencyUnavailable` и `DatabaseFailure` (параметризовано) | исключение пробрасывается без изменений |
| `test_pool_timeout_is_dependency_unavailable` | фабрика соединений поднимает `PoolTimeout` | `DependencyUnavailable(reason="db_unavailable")`; репозиторий не вызван; запись `db_query_failed` с `query = list_engineers` |

## `src/service/ticket_status.py` — переходы статусов заявки

Файл: `tests/service/test_ticket_status.py`.

> Замена стабами: репозиторий (`lock_ticket` — фейк, который возвращает заявку с заданным
> статусом или `None`; `update_ticket_status` — фейк, который возвращает заявку с новым
> статусом; оба могут поднять заданное исключение и запоминают вызовы), фабрика соединений —
> фейк, чьё соединение запоминает, чем закончилась транзакция (COMMIT или откат), и может
> поднять ошибку драйвера при фиксации. Логи —
> разбором JSON-строк stderr (`capsys`, `tests/log_records.py`).

| Test | Scenario | Expected result |
|---|---|---|
| `test_transition_table` (параметризован: все 49 пар «из → в» по 7 статусам) | заявка в статусе «из», запрос на статус «в» | разрешённый переход (таблица диаграммы `PATCH /api/v1/tickets/{ticket_id}/status`) — `update_ticket_status` вызван с новым статусом, возвращена заявка из него, транзакция зафиксирована; тот же статус — `update_ticket_status` не вызван, возвращена заявка как есть; остальные — `InvalidInput`, как в следующей строке |
| `test_transition_not_allowed` | заявка `completed`, запрос `en_route` | `InvalidInput(reason="transition_not_allowed")` с `message = "Статус заявки нельзя изменить с «Выполнена» на «В пути»"` и `params = {ticket_id, status_from: completed, status_to: en_route}`; `update_ticket_status` не вызван; транзакция откачена |
| `test_closed_ticket_stays_closed` (параметризован: `completed`, `cancelled` × остальные 6 статусов) | заявка в закрытом статусе, запрос на другой статус | `InvalidInput(reason="transition_not_allowed")`; `update_ticket_status` не вызван |
| `test_back_along_chain_not_allowed` (параметризован: `sent → not_sent`, `in_progress → en_route`, `in_progress → overdue`) | переход назад по цепочке или из `in_progress` в `overdue` | `InvalidInput(reason="transition_not_allowed")` |
| `test_forward_skip_allowed` | заявка `sent`, запрос `completed` | статус записан, `update_ticket_status` вызван один раз |
| `test_cancelled_after_dispatch` (параметризован: из `en_route` и `in_progress` → `true`; из `not_sent`, `sent`, `overdue` → `false`) | запрос `cancelled` | `update_ticket_status` вызван с `cancelled_after_dispatch` по параметру |
| `test_not_cancel_keeps_flag_false` | заявка `in_progress`, запрос `completed` | `update_ticket_status` вызван с `cancelled_after_dispatch = False` |
| `test_status_change_logged` | заявка `sent`, запрос `en_route` | одна запись `ticket_status_changed` уровня `info` с `ticket_id`, `status_from = sent`, `status_to = en_route`, после фиксации транзакции; адреса и других полей заявки в записи нет |
| `test_same_status_not_logged` | заявка `en_route`, запрос `en_route` | записи `ticket_status_changed` нет |
| `test_ticket_not_found` | `lock_ticket` вернул `None` | `NotFound(reason="ticket_not_found", params={ticket_id})`; `update_ticket_status` не вызван |
| `test_repository_failure_propagates` (параметризован: `lock_ticket` и `update_ticket_status` × `DependencyUnavailable`, `DatabaseFailure`) | репозиторий поднимает исключение | исключение пробрасывается без изменений; транзакция откачена; записи `ticket_status_changed` нет |
| `test_pool_timeout_is_dependency_unavailable` | фабрика соединений поднимает `PoolTimeout` | `DependencyUnavailable(reason="db_unavailable")`; репозиторий не вызван; запись `db_query_failed` с `query = change_ticket_status` |
| `test_commit_failure_is_dependency_unavailable` | статус записан, фиксация транзакции поднимает `OperationalError` | `DependencyUnavailable(reason="db_unavailable")`; одна запись `db_query_failed` с `query = change_ticket_status`; записи `ticket_status_changed` нет |

## `src/service/solver.py` — модель солвера, ступенчатая (лексикографическая) оптимизация

Файл: `tests/service/test_solver.py`.

> Мок не нужен: солвер — чистая функция, OR-Tools не мокается. Вход — маленький
> синтетический: 1–3 бригады, 1–8 заявок, матрицы времени и расстояния задаются в тесте по
> типам транспорта (секунды и метры), день плана — `2026-09-01`. Каждый результат проверяет
> независимая проверка допустимости `assert_feasible` (в тестовом модуле): каждая заявка —
> не больше одного раза и либо в маршруте, либо в неназначенных; у бригады маршрута есть
> навык заявки и требуемый транспорт; прибытие — точно самое раннее, что позволяет переезд
> по матрице профиля бригады (секунды вверх до минуты); начало работ — точно самое раннее из
> прибытия и начала окна; выезд не раньше начала смены; окончание последней работы не позже
> конца смены; `idle_min` бригады равен длине смены минус суммарные визиты и переезды.
> `SolveWithParameters` подменяется дважды: возвращает `None` в тесте ветки
> «решение не найдено», и вызовом, который поднимает исключение, если его вообще вызвали, —
> там, где заявка должна быть отсеяна раньше модели. Логи — разбором JSON-строк stderr
> (`capsys`, `tests/log_records.py`). Большинство сценариев вызывают `solve_day` напрямую и
> тем самым проверяют трёхфазную модель целиком; тесты этого раздела дополнительно
> сравнивают её с однопроходным взвешенным вариантом (`_solve_single_pass_weighted`) —
> базой сравнения, которая существует только для этого сравнения.

### Допустимость: навык и транспорт

| Test | Scenario | Expected result |
|---|---|---|
| `test_skill_required` | заявка `emergency`; бригада A без `emergency` ближе, бригада B с `emergency` дальше | заявка у B; `assert_feasible` проходит |
| `test_no_engineer_with_skill` | заявка `emergency`, ни у одной бригады нет `emergency` | заявка в неназначенных; маршрутов с визитами нет |
| `test_required_vehicle` | заявка требует `foot`; бригада с `car` ближе, бригада с `foot` дальше, обе с навыком | заявка у бригады с `foot` |
| `test_no_engineer_with_vehicle` | заявка требует `bike`; бригады с навыком — только `car` и `foot`; бригада с `bike` без навыка | заявка в неназначенных |
| `test_skill_and_vehicle_together` | 3 бригады: навык без транспорта, транспорт без навыка, навык и транспорт | заявка у третьей бригады |

### Время: окна, смены, переезды

| Test | Scenario | Expected result |
|---|---|---|
| `test_early_arrival_waits_for_window` | бригада со сменой с 10:00 доезжает за 10 мин, окно 12:00–14:00 | прибытие 10:10, начало работ 12:00, окончание — 12:00 + длительность |
| `test_arrival_inside_window` | окно 10:30–11:00, переезд 20 мин, смена с 10:00 | прибытие 10:20, начало работ 10:30 — не раньше начала окна |
| `test_window_unreachable` | окно 10:00–10:15, переезд 30 мин, смена с 10:00 | заявка в неназначенных |
| `test_window_outside_plan_day` | окно заявки на следующий день | заявка в неназначенных, OR-Tools её не получает |
| `test_window_starts_the_day_before` | окно открылось накануне 22:00, закрывается 11:00 | внутри дня окно зажато с полуночи; начало работ — не раньше выезда бригады |
| `test_window_ends_the_day_after` | окно закрывается в 1:00 следующих суток, смена до 23:59, работа 30/70 мин | 30 мин — назначена; 70 мин — в неназначенных: не успевает до конца суток |
| `test_window_with_seconds_rounds_up` | окно открывается в 10:00:30 | начало работ — 10:01, не раньше 10:00:30 |
| `test_departure_not_before_shift` | смена с 15:30, окно 10:00–16:00, переезд 10 мин | прибытие не раньше 15:40, начало работ 15:40 |
| `test_work_ends_within_shift` | смена до 18:00, окно 17:00–17:30, работа 70 мин | заявка в неназначенных: работа закончилась бы в 18:10 |
| `test_return_trip_not_counted` | смена до 18:00, работа заканчивается в 17:55, обратный путь к старту 60 мин | заявка назначена: маршрут открытый |
| `test_shift_capacity` | 1 бригада, смена 10:00–12:00, 4 заявки по 50 мин с широкими окнами и переездом 5 мин | назначены 2, остальные в неназначенных; окончание последней работы не позже 12:00 |
| `test_travel_by_engineer_profile` | 2 бригады с одним навыком, `car` и `foot`, из одной точки; по матрице `car` 10 мин, по `foot` 60 мин; окно 10:00–10:30 | заявка у бригады с `car`; прибытие 10:10 |
| `test_no_route_between_points` | в матрице профиля бригады A между её стартом и заявкой нет маршрута (`None`), у B маршрут есть | заявка у B; при единственной бригаде A — в неназначенных |
| `test_travel_rounded_up_to_minute` | переезд 61 с | переезд 2 мин; прибытие = выезд + 2 мин |
| `test_times_naive_whole_minutes` | любой план | все моменты — наивные `datetime` дня плана с нулевыми секундами |

### Целевая функция

| Test | Scenario | Expected result |
|---|---|---|
| `test_emergency_over_any_lower` | 1 бригада, в смене помещается только одно из: 1 авария или 3 подключения | назначена авария, 3 подключения в неназначенных |
| `test_connection_over_repairs` | 1 бригада, помещается только одно из: 1 подключение или 2 ремонта | назначено подключение |
| `test_fewer_engineers_preferred` | 2 одинаковые бригады, 3 заявки умещаются в смену одной | все 3 назначены одной бригаде; у второй нет визитов |
| `test_coverage_over_engineers` | 3 заявки умещаются только у двух бригад | назначены все 3, задействованы 2 бригады |
| `test_shorter_order_chosen` | 1 бригада, 3 заявки на прямой, окна на весь день | порядок посещения по прямой от старта; суммарный переезд минимален |

### Ступенчатая (лексикографическая) оптимизация

| Test | Scenario | Expected result |
|---|---|---|
| `test_lexicographic_uses_no_more_engineers_than_single_pass` | 4 бригады, навык только у 2 (дефицит), 6 заявок навыка | лексикографический план задействует не больше бригад, чем однопроходный взвешенный на тех же данных; на этом конкретном входе обе стратегии умещаются на одной бригаде (1 ≤ 1) — расхождение проверяет случайный компаньон ниже |
| `test_lexicographic_uses_no_more_engineers_than_single_pass_random` (seed 0–9) | случайные входы `_random_instance` | то же сравнение на 10 случайных наборах |
| `test_solver_phase_finished_logged` | обычный вход | 3 записи `solver_phase_finished` уровня `info`, `phase` по порядку 1, 2, 3, у каждой — целое `objective` и `duration_ms` |
| `test_idle_time_computed` | 1 бригада, 1 визит с переездом и длительностью | `idle_min` = длина смены минус переезд минус длительность |
| `test_idle_time_whole_shift_when_unused` | бригада без подходящего навыка, заявка неназначена | `idle_min` = длина смены целиком |
| `test_bound_coverage_and_bound_fleet_actually_cut` | `_bound_coverage`/`_bound_fleet` напрямую: недостижимый штраф покрытия; штраф в 0 (полное покрытие обязательно) вместе с нулём разрешённых бригад | оба случая — модель недопустима, ограничения реально отсекают решения, а не только присутствуют |

### Бригада — одна «машина»; результат

| Test | Scenario | Expected result |
|---|---|---|
| `test_route_per_engineer` | 3 бригады, 8 заявок | по одному маршруту на каждую бригаду, в порядке бригад входа; каждая заявка ровно один раз — в маршруте или в неназначенных |
| `test_visit_fields` | 1 бригада, 2 заявки | у визита: id заявки, прибытие, начало и окончание работ, переезд в минутах и метрах из матриц профиля бригады |
| `test_random_instances_feasible` | 20 случайных входов (seed 0–19): 3 бригады со случайными навыками, транспортом и сменами, 8 заявок со случайными окнами | `assert_feasible` проходит на каждом |
| `test_no_engineers` | ноль бригад, 2 заявки | `OPTIMAL`, маршрутов нет, обе заявки в неназначенных; OR-Tools не вызван |
| `test_no_tickets` | 2 бригады, ноль заявок | `OPTIMAL`, маршруты обеих бригад без визитов |
| `test_matrix_size_mismatch` | число точек матрицы не равно бригады + заявки | `ValueError` |
| `test_missing_matrix_for_vehicle` | у бригады `bike`, матрицы `bike` нет | `ValueError` |
| `test_shift_start_not_before_end_rejected` | у бригады смена задана с 20:00 по 10:00 | `ValueError`, проверка до вызова OR-Tools |

### Статус решения и логи

| Test | Scenario | Expected result |
|---|---|---|
| `test_penalties_reject_too_many_ranks` | сумма штрафов приближается к переполнению int64 | `ValueError` |
| `test_penalties_dominate_strictly` | 3 ранга приоритета с разным числом заявок | штраф более срочного ранга больше суммы штрафов всех менее срочных вместе |
| `test_status_feasible_or_optimal` | обычный вход | статус `OPTIMAL` или `FEASIBLE`; запись `solver_finished` уровня `info` со `status`, `duration_ms`, `vehicles`, `nodes`, `dropped` |
| `test_no_solution` | `SolveWithParameters` возвращает `None` | статус `INFEASIBLE`, маршрутов нет; запись `solver_finished` уровня `warning` со `status = INFEASIBLE` |
| `test_logs_no_ticket_data` | план с назначенными и неназначенными заявками | в записях лога нет id заявок, точек и адресов — только статус и счётчики |

### Проверка допустимости `assert_feasible` ловит нарушение

| Test | Scenario | Expected result |
|---|---|---|
| `test_checker_fails_on_skill` | план, где заявка у бригады без её навыка | `AssertionError` |
| `test_checker_fails_on_vehicle` | заявка с требуемым транспортом у бригады с другим | `AssertionError` |
| `test_checker_fails_on_window` | начало работ после окончания окна; прибытие раньше, чем позволяет переезд | `AssertionError` |
| `test_checker_fails_on_shift` | выезд раньше начала смены; окончание работ позже конца смены | `AssertionError` |

## `src/service/baseline.py` — baseline FCFS

Файл: `tests/service/test_baseline.py`.

> Мок не нужен: baseline — чистая функция, как и солвер, OR-Tools не используется. Вход —
> маленький синтетический: 1–3 бригады, 1–8 заявок, матрицы времени и расстояния задаются в
> тесте по типам транспорта (секунды и метры), день плана — `2026-09-01`. Каждый результат
> проверяет независимая проверка допустимости `assert_feasible_fcfs` (в тестовом модуле):
> заявка — не больше одного раза и либо в маршруте, либо в неназначенных; у бригады маршрута
> есть навык заявки и требуемый транспорт; прибытие — точно самое раннее, что позволяет
> переезд от предыдущей точки бригады (секунды вверх до минуты); начало работ — самое раннее
> из прибытия и начала окна, без округления начала окна (в отличие от целочисленной по
> минутам модели солвера); окончание последней работы не позже конца смены; визиты бригады
> идут в порядке, в котором заявки были ей назначены; `idle_min` равен длине смены минус
> суммарные визиты и переезды.

### Порядок и первое подходящее назначение

| Test | Scenario | Expected result |
|---|---|---|
| `test_input_order_ticket_processing` | заявка низкого приоритета первая во входном списке, аварийная — последняя; обе умещаются только у одной бригады | назначена заявка низкого приоритета (пришла первой), аварийная — в неназначенных; приоритет не влияет на порядок обработки |
| `test_first_fit_engineer_no_backtracking` | 2 подходящие бригады: первая по входному порядку дальше, вторая ближе | заявка у первой бригады по входному порядку, а не у ближайшей |
| `test_visit_order_matches_assignment_order` | 2 заявки одной бригаде: у второй заявки окно раньше, чем у первой, но первая пришла раньше во входном списке и назначена первой | маршрут бригады: первая заявка визитом раньше второй — порядок визитов равен порядку назначения, а не порядку окон |
| `test_no_global_reoptimization` | 3-я заявка подошла бы лучше между уже назначенными 1-й и 2-й (короче суммарный переезд), чем в конец маршрута | заявка вставлена в конец маршрута, порядок первых двух визитов не изменился |

### Допустимость: навык и транспорт

| Test | Scenario | Expected result |
|---|---|---|
| `test_skill_required` | заявка `emergency`; бригада A без `emergency` первая по входу, бригада B с `emergency` вторая | заявка у B |
| `test_no_engineer_with_skill` | заявка `emergency`, ни у одной бригады нет `emergency` | заявка в неназначенных |
| `test_required_vehicle` | заявка требует `car`; первая по входу бригада — `foot` с навыком, вторая — `car` с навыком | заявка у бригады с `car` |
| `test_no_engineer_with_vehicle` | заявка требует `bike`; бригады с навыком — только `car` и `foot` | заявка в неназначенных |

### Время: окна, смены, переезды

| Test | Scenario | Expected result |
|---|---|---|
| `test_early_arrival_waits_for_window` | бригада со сменой с 10:00 доезжает за 10 мин, окно 12:00–14:00 | прибытие 10:10, начало работ 12:00 — точно начало окна, без округления до минуты |
| `test_window_unreachable` | окно 10:00–10:15, переезд 30 мин, единственная подходящая бригада со сменой с 10:00 | заявка в неназначенных |
| `test_shift_not_enough_tries_next_engineer` | у первой по входу бригады заявка не укладывается в смену, у второй — укладывается | заявка у второй бригады |
| `test_no_route_tries_next_engineer` | в матрице первой по входу бригады до заявки нет маршрута (`None`), у второй маршрут есть | заявка у второй бригады |
| `test_travel_rounded_up_to_minute` | переезд 61 с | переезд 2 мин; прибытие = свободна с + 2 мин |
| `test_travel_from_previous_visit` | у бригады уже есть визит; вторая заявка ближе к точке первой заявки, чем к точке старта бригады | переезд второй заявки считается от точки первой, а не от старта |

### Результат и независимость от солвера

| Test | Scenario | Expected result |
|---|---|---|
| `test_status_always_optimal` | вход, на котором часть заявок остаётся неназначенной | `status = OPTIMAL`: baseline не ищет решение, поэтому не может его не найти |
| `test_output_shares_dayplan_shape` | один и тот же вход подан и солверу (`solve_day`), и baseline | оба возвращают `DayPlan` с маршрутами `EngineerRoute`/`Visit` одной формы полей — планы сравнимы по составу метрик без отдельного маппинга |
| `test_route_per_engineer` | 3 бригады, 8 заявок | по одному маршруту на каждую бригаду, в порядке бригад входа |
| `test_visit_fields` | 1 бригада, 2 заявки | у визита: id заявки, прибытие, начало и окончание работ, переезд в минутах и метрах из матриц профиля бригады |
| `test_random_instances_feasible` | 20 случайных входов (seed 0–19): 3 бригады со случайными навыками, транспортом и сменами, 8 заявок со случайными окнами | `assert_feasible_fcfs` проходит на каждом |
| `test_idle_time_computed` | 1 бригада, 1 визит с переездом и длительностью | `idle_min` = длина смены минус переезд минус длительность |
| `test_idle_time_whole_shift_when_unused` | бригада без подходящего навыка, заявка неназначена | `idle_min` = длина смены целиком |
| `test_no_engineers` | ноль бригад, 2 заявки | маршрутов нет, обе заявки в неназначенных |
| `test_no_tickets` | 2 бригады, ноль заявок | маршруты обеих бригад без визитов |
| `test_matrix_size_mismatch` | число точек матрицы не равно бригады + заявки | `ValueError` |
| `test_matrix_size_mismatch_asymmetric` | `durations_s` короче на одну строку, `distances_m` длиннее на одну — суммарно совпадает с верным размером | `ValueError`: размер каждой матрицы проверяется отдельно, а не только их сумма |
| `test_missing_matrix_for_vehicle` | у бригады `bike`, матрицы `bike` нет | `ValueError` |
| `test_shift_start_not_before_end_rejected` | у бригады смена задана с 20:00 по 10:00 | `ValueError` |

### Логи

| Test | Scenario | Expected result |
|---|---|---|
| `test_baseline_finished_logged` | обычный вход | запись `baseline_finished` уровня `info` с `duration_ms`, `vehicles`, `nodes`, `dropped` |
| `test_logs_no_ticket_data` | план с назначенными и неназначенными заявками | в записи лога нет id заявок, точек и адресов — только счётчики |

## `src/service/explain.py` — атрибуция причины отказа и объяснения

Файл: `tests/service/test_explain.py`.

> Мок не нужен: чистая функция над уже построенным `DayPlan` (солвера или baseline), без БД,
> OSRM и OR-Tools. Вход — маленький синтетический: 1–3 бригады, 1–8 заявок, матрицы времени и
> расстояния по типам транспорта (секунды и метры), день плана — `2026-09-01`; те же заявки,
> бригады и матрицы, что были переданы алгоритму, который построил план. Логи — разбором
> JSON-строк stderr (`capsys`, `tests/log_records.py`).

### Проходит без изменений

| Test | Scenario | Expected result |
|---|---|---|
| `test_infeasible_passthrough` | план со статусом `INFEASIBLE` | `ExplainedPlan` с тем же статусом, без маршрутов и без неназначенных; никаких записей лога |

### Назначенные заявки: текст

| Test | Scenario | Expected result |
|---|---|---|
| `test_assigned_explanation_fields` | 1 бригада, 1 визит `connection`, переезд 18 мин | текст содержит название бригады, русский навык («Подключение»), окно заявки, русский вид транспорта и `18 мин`; в тексте нет служебных терминов солвера (штраф, dimension, allowed vehicles) |
| `test_assigned_explanation_uses_own_window_not_computed_start` | окно заявки 10:00–14:00, расчётное начало работ (после ожидания) — 10:30 | текст называет окно заявки 10:00–14:00, а не 10:30 |

### Атрибуция причины: пять групп ограничений по порядку

| Test | Scenario | Expected result |
|---|---|---|
| `test_no_skill` | заявка `emergency`, ни у одной бригады региона нет `emergency` | `reason = no_skill` |
| `test_no_vehicle` | заявка требует `bike`; бригады с навыком — только `car` и `foot` | `reason = no_vehicle` |
| `test_no_time_slot` | единственная подходящая по навыку/транспорту бригада: окно 10:00–10:15, переезд от её старта — 30 мин | `reason = no_time_slot` |
| `test_shift_overflow` | подходящая бригада успевает в окно, но её смена кончается раньше, чем закончилась бы работа | `reason = shift_overflow` |
| `test_no_time_slot_before_shift_overflow` | 2 подходящие бригады: у одной окно недостижимо, у другой окно достижимо, но не хватает смены | `reason = shift_overflow` — достаточно одной бригады с достижимым окном, чтобы код не был `no_time_slot` |
| `test_all_eligible_engineers_booked_elsewhere` | подходящая по навыку/транспорту/окну/смене бригада есть, но в плане её маршрут занят другой заявкой в это время | `reason = all_eligible_engineers_booked_elsewhere` |
| `test_attribution_ignores_actual_route` | бригада технически подходит по навыку/транспорту/окну/смене без учёта своего маршрута в плане | шаги 1–3 атрибуции пропускают её текущий маршрут: используются только её точка старта и её смена, не то, чем она занята в плане |
| `test_no_route_excludes_candidate` | в матрице подходящей по навыку бригады до заявки нет маршрута (`None`) | бригада не считается кандидатом на шаге окна/смены — как если бы окно было недостижимо |

### Неназначенные заявки: текст

| Test | Scenario | Expected result |
|---|---|---|
| `test_unassigned_explanation_fields` (параметризован по каждому коду причины) | заявка неназначена по каждому из пяти кодов | текст содержит навык и (если задан) требуемый транспорт заявки; окно — там, где оно и есть причина (`no_time_slot`, `shift_overflow`, `all_eligible_engineers_booked_elsewhere`), но не в `no_skill`/`no_vehicle` — там ни одна бригада не дошла до проверки окна; для `all_eligible_engineers_booked_elsewhere` — ещё число технически подходящих бригад; текстов без терминов солвера |

### Согласованность входа

| Test | Scenario | Expected result |
|---|---|---|
| `test_matrix_size_mismatch_rejected` | число точек матрицы не равно бригады + заявки | `ValueError` — тот же контракт входа, что у солвера и baseline, которые эту матрицу построили |
| `test_missing_matrix_for_vehicle_rejected` | у бригады `bike`, матрицы `bike` нет | `ValueError` |

### Логи

| Test | Scenario | Expected result |
|---|---|---|
| `test_unassigned_reason_attributed_logged` | 2 неназначенные заявки, разные коды | 2 записи `unassigned_reason_attributed` уровня `debug`, у каждой — `ticket_id`, `reason_code`; ни одной по назначенным |
| `test_unassigned_reasons_summary_logged` | 3 неназначенные: 2 `no_skill`, 1 `shift_overflow` | 1 запись `unassigned_reasons_summary` уровня `info` со счётчиками `{"no_skill": 2, "shift_overflow": 1}` |
| `test_logs_no_ticket_data_beyond_id` | план с назначенными и неназначенными заявками | ни в одной записи лога нет адресов, точек и текста объяснения — только `ticket_id`, коды причин и счётчики |

## `src/service/plan_builder.py` — постановка в очередь и фоновая сборка плана

Файл: `tests/service/test_plan_builder.py`.

> Замена стабами: `connect`/`get_region_id`/`list_open_tickets`/`list_engineers`/
> `insert_running_plan`/`mark_plan_done`/`mark_plan_failed` — асинхронные функции без
> реальной БД; OSRM — фейк с `table()`, возвращающий заданные матрицы или ошибку; пул
> солвера — `SyncPool` (наследник `concurrent.futures.Executor`), выполняющий переданную
> функцию синхронно в текущем процессе вместо реального подпроцесса. `solve_day`,
> `baseline.solve_day` и `explain` вызываются по-настоящему — на входе в 1 бригаду и 1
> заявку, без нужды подделывать их результат.

### `enqueue`

| Test | Scenario | Expected result |
|---|---|---|
| `test_enqueue_queues_a_running_plan` | валидный вход | `QueuedPlan` с `plan_id`, `algorithm` и теми же `tickets`/`engineers`, что вернули стабы |
| `test_enqueue_unknown_region` | код региона не из `regions.toml` | `InvalidInput(reason="unknown_region")`; строка плана не вставляется |
| `test_enqueue_region_not_loaded` | `get_region_id` возвращает `None` | `InvalidInput(reason="region_not_loaded")` |
| `test_enqueue_plan_date_mismatch` | у заявки окно не на дату плана | `InvalidInput(reason="plan_date_mismatch")` |
| `test_enqueue_too_many_points` | бригад + заявок больше `max_table_size` | `InvalidInput(reason="too_many_points")` |
| `test_enqueue_insert_failure_propagates` | `insert_running_plan` поднимает `DependencyUnavailable` | ошибка поднята как есть |

### `build`

| Test | Scenario | Expected result |
|---|---|---|
| `test_build_or_tools_persists_done` | `algorithm="or_tools"`, OSRM отвечает | `mark_plan_done` вызван с назначениями по заявке |
| `test_build_baseline_persists_done` | `algorithm="baseline_fcfs"` | то же, солвер (пул) не используется |
| `test_build_no_engineers_no_matrix_calls` | 0 бригад | OSRM не вызывается ни для одного типа транспорта; заявка уходит неназначенной |
| `test_build_osrm_unavailable_marks_failed` | OSRM поднимает `DependencyUnavailable` | план помечен `status=failed, failed_reason=osrm_unavailable`; `mark_plan_done` не вызван |
| `test_build_unexpected_error_marks_build_error` | OSRM поднимает `ValueError` | `status=failed, failed_reason=build_error`; запись лога `plan_build_failed` уровня `error` |
| `test_build_persist_dependency_unavailable_marks_failed` | `mark_plan_done` поднимает `DependencyUnavailable` | `status=failed, failed_reason=db_unavailable` |
| `test_build_persist_database_failure_marks_build_error` | `mark_plan_done` поднимает `DatabaseFailure` | `status=failed, failed_reason=build_error` (уже залогировано `database_errors`, повторно не логируется) |
| `test_build_mark_failed_swallows_its_own_failure` | и `mark_plan_done`, и `mark_plan_failed` падают | `build` не поднимает исключение — план остаётся `running`, как после рестарта backend |
| `test_build_logs_finished` | успешное построение | запись `plan_build_finished` с `plan_id` и `algorithm` |

## `src/service/plan_reader.py` — чтение плана

Файл: `tests/service/test_plan_reader.py`.

> Замена стабами: `connect`/`get_plan`/`list_engineers`/`list_plan_assignments` — без
> реальной БД. Идентичность бригады и её визитов проверяется на маленьком синтетическом
> входе (1–2 бригады, 1–2 назначения).

| Test | Scenario | Expected result |
|---|---|---|
| `test_plan_not_found` | `get_plan` возвращает `None` | `NotFound(reason="plan_not_found")` |
| `test_running_plan_has_no_routes` | `status="running"` | `engineers`/`unassigned`/`metrics` — `None` |
| `test_failed_plan_carries_reason` | `status="failed"`, `failed_reason` задан | тот же `failed_reason` в ответе; `engineers`/`unassigned`/`metrics` — `None` |
| `test_done_plan_lists_every_region_engineer` | 2 бригады региона, назначение только у одной | обе в ответе, по возрастанию `engineer_id`; у незадействованной — пустой маршрут |
| `test_visit_fields_and_distance_rounding` | визит с `travel_distance_m=1234` | `travel_distance_km == 1.2` (округление до 0.1 км), остальные поля визита как в строке |
| `test_idle_time_is_shift_minus_travel_and_duration` | смена 120 мин, 2 визита (15+5 мин переезда, 30+20 мин на объекте) | `idle_time_min == 120 - 20 - 50` |
| `test_visits_sorted_by_sequence_no` | строки назначений в БД в произвольном порядке | маршрут отсортирован по `sequence_no` |
| `test_engineer_without_assignments_has_full_shift_idle` | у бригады нет ни одного назначения | `idle_time_min` — вся смена, `total_travel_time_min`/`total_distance_km` — 0 |
| `test_get_plan_dependency_unavailable_propagates` | `get_plan` поднимает `DependencyUnavailable` | ошибка поднята как есть |
| `test_metrics_engineers_used_counts_used_only` | 2 бригады региона, у одной 1 визит, у другой ни одного | `metrics.engineers_used == 1` |
| `test_metrics_total_distance_km_sums_all_routes` | 2 бригады с маршрутами по 21.4 и 14.0 км | `metrics.total_distance_km == 35.4` |
| `test_metrics_distance_and_idle_by_engineer_cover_every_engineer` | 2 бригады региона, у одной нет визитов | `distance_by_engineer` и `idle_time_by_engineer_min` содержат ключ каждой бригады (`engineer_id`), включая незадействованную — с 0 км и полной сменой простоя |
| `test_metrics_assigned_and_unassigned_counts` | 2 назначенные заявки одной бригаде, 1 неназначенная | `assigned_count == 2`, `unassigned_count == 1` |

### `compare`

> Каждый план читается тем же путём, что и в `get` (`FakeRepo`, ключ — `plan_id`); синтетический
> вход — 2 плана с разными `metrics`, не сами построение или бригады.

| Test | Scenario | Expected result |
|---|---|---|
| `test_compare_returns_engineers_used_and_total_distance_km` | план (`engineers_used=2, total_distance_km=30.0`), baseline (`engineers_used=3, total_distance_km=40.0`), оба `done` | список из 2 записей, `metric` по порядку `engineers_used`, `total_distance_km`; `main`/`baseline` — значения соответствующего плана |
| `test_compare_delta_is_main_minus_baseline` | `total_distance_km`: main 30.0, baseline 40.0 | `delta == -10.0` у записи `total_distance_km` |
| `test_compare_excludes_idle_time` | оба плана `done` | среди `metric` двух записей ответа нет `idle_time` |
| `test_compare_main_not_found` | `get_plan(plan_id)` вернул `None` | `NotFound(reason="plan_not_found", params={"plan_id": ...})`; план-baseline не читается |
| `test_compare_baseline_not_found` | план из пути `done`, `get_plan(baseline_plan_id)` вернул `None` | `NotFound(reason="plan_not_found", params={"plan_id": <baseline_plan_id>})` |
| `test_compare_main_not_ready` (параметризован: `status="running"`, `status="failed"`) | план из пути не `done` | `InvalidInput(reason="plan_not_ready")`; план-baseline не читается |
| `test_compare_baseline_not_ready` (параметризован: `status="running"`, `status="failed"`) | план из пути `done`, план-baseline не `done` | `InvalidInput(reason="plan_not_ready")` |
| `test_compare_dependency_unavailable_propagates` | `get_plan` любого из двух планов поднимает `DependencyUnavailable` | ошибка поднята как есть |

## `src/service/replan.py` — перепланирование по событию (Contract Net)

Файл: `tests/service/test_replan.py`.

> Замена стабами: `connect`/`get_plan`/`list_engineers`/`list_tickets`/`list_plan_assignments`/
> `insert_ticket`/`insert_replanned_plan` — без реальной БД (`FakeRepo`, `tests/service/test_replan.py`).
> OSRM — `FakeOsrm`: любой перегон занимает ровно 5 минут (300 с) и 1 км, кроме точки до
> самой себя, так что времена прибытия в тестах считаются вручную. `clock` — фиксированное
> время.

| Test | Scenario | Expected result |
|---|---|---|
| `test_assigns_to_sole_candidate_with_empty_tail` | одна бригада с навыком `emergency`, у неё нет визитов | авария вставлена ей первым визитом; `diff.newly_assigned == [<id новой заявки>]`, `plan_stability == 1`; вставленная заявка — `required_skill=emergency`, `priority=1`, `duration_min=80` |
| `test_no_skilled_engineer_leaves_incident_unassigned` | ни у одной бригады региона нет навыка `emergency` | заявка вставлена в БД, но её строка в новом плане — `engineer_id=None`, `unassigned_reason="no_skill"`; `diff.plan_stability == 0` |
| `test_vehicle_mismatch_leaves_incident_unassigned_no_vehicle` | у бригады есть навык `emergency`, но не тот транспорт, что требует авария | `unassigned_reason="no_vehicle"` |
| `test_assigns_past_reaction_target_when_no_faster_candidate` | единственный кандидат может успеть только заметно позже `reaction_min` (вставка аварии после уже стоящей заявки с узким окном) | авария всё равно назначена этой бригаде; `explanation` содержит «превышает целевую реакцию» |
| `test_in_progress_visit_is_carried_forward_unchanged_on_touched_engineer` | у бригады-победителя есть визит `in_progress` (заморожен) и один открытый визит в хвосте | строка замороженного визита переносится без изменений (`sequence_no=1`, то же `planned_arrival`/`explanation`), не входит в `diff.changed_assignments`; авария и открытый визит получают следующие по порядку `sequence_no` |
| `test_eviction_reoffers_blocking_ticket_to_another_brigade` | у бригады-победителя единственный визит в хвосте с узким окном и короткой сменой — ни одна из двух позиций вставки не проходит без вытеснения | визит вытеснен и переставлен на другую бригаду с тем же навыком; `explanation` обеих строк называет причину («вытеснением»/«переставлена»); `diff.changed_assignments` содержит вытесненную заявку, `plan_stability == 2` |
| `test_eviction_without_matching_reoffer_candidate_unassigns_evicted_ticket` | как выше, но других бригад с нужным навыком нет | авария вставлена вытеснением, вытесненная заявка — `unassigned_reason="no_skill"`, входит в `diff.newly_unassigned` |
| `test_ticket_cancelled_drops_visit_and_shifts_the_tail` | у бригады отменённый визит и один открытый визит после него | строки отменённого визита в новом плане нет вовсе; открытый визит получает `sequence_no=1` и пересчитанное время; `diff.changed_assignments` содержит его (сменился `sequence_no`) |
| `test_ticket_cancelled_ticket_not_found` | `ticket_id` события не входит в заявки региона | `NotFound(reason="ticket_not_found")` |
| `test_ticket_cancelled_ticket_not_yet_cancelled` | заявка существует, но её статус не `cancelled` | `Conflict(reason="ticket_not_cancelled")` |
| `test_plan_not_done_is_rejected` | план-родитель `status="running"` | `InvalidInput(reason="plan_not_ready")` |
| `test_plan_not_found` | `get_plan` вернул `None` | `NotFound(reason="plan_not_found")` |
| `test_triggered_at_outside_plan_date_is_rejected` | `triggered_at` — другая календарная дата, чем `plan_date` | `InvalidInput(reason="triggered_at_out_of_range")` |
| `test_untouched_engineer_row_is_copied_forward_unchanged` | бригада без навыка `emergency` с уже назначенной заявкой | её строка в новом плане совпадает со строкой плана-родителя дословно; заявка не входит в `diff.changed_assignments` |

## `api` — POST /api/v1/plan/{plan_id}/replan

Файл: `tests/api/test_replan.py`.

> Замена стабами: `Replanner` — фейк через `app.dependency_overrides` (`FakeReplanner` в
> `tests/api/region_fakes.py`), запоминает вызовы и возвращает заданный `ReplanOutcome` или
> поднимает заданное исключение; `PlanReader` — тот же `FakePlanReader`, что и у остальных
> `plan`-маршрутов (маршрут дочитывает engineers/unassigned/metrics нового плана им же).

| Test | Scenario | Expected result |
|---|---|---|
| `test_replan_new_urgent_ticket_returns_the_new_plan` | валидное тело `new_urgent_ticket`, `Replanner.replan` вернул `ReplanOutcome` с непустым `diff` | `200`, тело `PlanReplanResult` — `plan_id`/`parent_plan_id`/`status=done` из исхода, `engineers`/`unassigned`/`metrics` из `PlanReader.get`, `diff` — как вернул сервис, `reassigned_from_unavailable_engineer` всегда `[]`; событие дошло до `Replanner.replan` разобранным (`NewUrgentTicketEvent` с полями заявки и `reaction_min`) |
| `test_replan_ticket_cancelled_reaches_the_service` | валидное тело `ticket_cancelled` | `Replanner.replan` вызван с `TicketCancelledEvent(ticket_id=...)` |
| `test_replan_default_reaction_min_is_120` | тело без `reaction_min` | событию передан `reaction_min == 120` |
| `test_replan_rejects_malformed_body` (параметризован: пустое тело, неизвестный `event_type`, лишнее поле, `ticket_id=0`) | запрос с таким телом | `400` |
| `test_replan_invalid_triggered_at_date` | `triggered_at="2026-02-30T12:00:00"` (несуществующая дата, форму спека принимает) | `400`, `{"fields": [{"name": "triggered_at", "message": "Несуществующие дата или время"}]}` |
| `test_replan_plan_not_found` | `Replanner.replan` поднимает `NotFound` | `404` |
| `test_replan_plan_not_ready` | `Replanner.replan` поднимает `InvalidInput(reason="plan_not_ready")` | `400` |
| `test_replan_ticket_not_cancelled_is_conflict` | `Replanner.replan` поднимает `Conflict(reason="ticket_not_cancelled")` | `409` |
| `test_replan_dependency_failure` (параметризован: `DependencyUnavailable`, `DatabaseFailure`) | `Replanner.replan` поднимает эту ошибку | `503` \| `500` без тела |
## `src/clients/nominatim.py` — клиент Nominatim

Файл: `tests/clients/test_nominatim.py`.

> Замена стабами: HTTP — `httpx.MockTransport` с заданными ответами; время — фейковые часы и
> `sleep`, которые запоминают паузы. Реальных сетевых вызовов нет.

| Test | Scenario | Expected result |
|---|---|---|
| `test_search_found` | ответ `200` с одним результатом `lat`/`lon` строками | `Point(lat, lon)` как числа; запрос `GET /search` с `format=jsonv2`, `countrycodes=ru`, `limit=1`, заголовком `User-Agent` из настроек; запись `nominatim_request_finished` уровня `debug` с `status = 200`, `found = true`, `duration_ms` |
| `test_search_not_found` | ответ `200 []` | `None`; `nominatim_request_finished` с `found = false` |
| `test_rate_limit` | три запроса подряд | между началом соседних запросов не меньше 1 с (по фейковым часам) |
| `test_rate_limit_concurrent` | три запроса одновременно (`asyncio.gather`) | между началом соседних запросов не меньше 1 с |
| `test_server_error` | ответ `503` | `DependencyUnavailable(reason="geocoder_unavailable")`; запись `nominatim_request_failed` с `status = 503`, `duration_ms` |
| `test_rate_limited_or_forbidden` | ответ `429` и `403` | `DependencyUnavailable`; `nominatim_request_failed` с кодом |
| `test_timeout_and_network_error` | транспорт поднимает `httpx.ConnectTimeout` и `httpx.ConnectError` | `DependencyUnavailable`; `nominatim_request_failed` без `status` |
| `test_malformed_response` | `200` с телом не JSON и JSON без `lat` | `DependencyUnavailable`; `nominatim_request_failed` |
| `test_logs_no_address` | любой запрос | адреса нет ни в одной записи лога |

## `src/clients/osrm.py` — клиент OSRM

Файл: `tests/clients/test_osrm.py`.

> Замена стабами: HTTP — по одному `httpx.MockTransport` на граф (`car`, `foot`, `bike`) с
> заданными ответами; каждый транспорт запоминает пришедшие запросы. Реальных сетевых
> вызовов нет. В тестах `public_transport_factor = 1.5`, `max_table_size = 1000`, если в
> строке не сказано иное.

### Матрица `table`

| Test | Scenario | Expected result |
|---|---|---|
| `test_table_car` | `table(car, [A, B])`, граф `car` отвечает `200 {code: Ok, durations, distances}` | `TravelMatrix` с `durations_s` и `distances_m` из ответа (секунды, метры, дробные); один запрос `GET /table/v1/car/{lonA},{latA};{lonB},{latB}` с `annotations=duration,distance` и без `sources` — координаты в порядке `lon,lat`, с пятью знаками после запятой (около метра: `55.751244` уходит как `55.75124`); запись `osrm_request_finished` уровня `debug` с `endpoint = table`, `profile = car`, `points = 2`, `status = 200`, `duration_ms` |
| `test_table_uses_graph_of_vehicle` (параметризован: `car`, `foot`, `bike`) | `table(vehicle, [A, B])` | запрос пришёл только в транспорт графа этого профиля, путь `/table/v1/{profile}/…`; в два других графа запросов нет; матрица — ответ этого графа без изменений |
| `test_table_public_transport_is_car_times_factor` | `table(public_transport, [A, B])`, граф `car` отвечает `durations [[0, 600], [700, 0]]`, `distances [[0, 5000], [5200, 0]]` | запрос ушёл в граф `car`; `durations_s == [[0, 900], [1050, 0]]`, `distances_m` — без изменений; в записи лога `profile = car` |
| `test_table_empty_points` | `table(car, [])` | пустая матрица, запросов нет |
| `test_table_single_point` (параметризован: `car`, `public_transport`) | `table(vehicle, [A])`; граф ответил бы `400 InvalidOptions` — так `osrm-routed` отвечает на таблицу из одной точки | `TravelMatrix([[0.0]], [[0.0]])`, запросов нет |
| `test_table_null_cell_is_none` (параметризован: `car`, `public_transport`) | в ответе `durations[0][1] = null`, `distances[0][1] = null` | соответствующие ячейки — `None`: не ноль и не расстояние по прямой; у `public_transport` `None` остаётся `None` |
| `test_table_in_strips_over_limit` | `max_table_size = 3`, `table(car, [A, B, C, D])` (16 ячеек > 9) | два запроса: все 4 точки в пути, `sources=0;1` и `sources=2;3` (по 2 источника: 2 × 4 ≤ 9); строки матрицы склеены по порядку источников — 4 × 4; два `osrm_request_finished` |
| `test_table_strip_failure_fails_whole_matrix` | `max_table_size = 3`, 4 точки; первая полоса — `200`, вторая — `503` | `DependencyUnavailable(reason="osrm_unavailable")`, неполная матрица не возвращается |
| `test_table_server_error` | ответ `503` | `DependencyUnavailable(reason="osrm_unavailable")`; запись `osrm_request_failed` уровня `error` с `endpoint = table`, `profile`, `points`, `status = 503`, `error = http_error` (тело не JSON), `duration_ms` |
| `test_table_error_code` (параметризован: `TooBig`, `NoSegment`, `InvalidQuery`) | ответ `400 {code: <код>, message: …}` | `DependencyUnavailable(reason="osrm_unavailable")`; `osrm_request_failed` со `status = 400`, `error = <код>` |
| `test_table_timeout_and_network_error` | транспорт поднимает `httpx.ReadTimeout` и `httpx.ConnectError` | `DependencyUnavailable`; `osrm_request_failed` без `status`, `error` — класс исключения |
| `test_table_url_too_long` | `table(car, …)` по 4000 точкам (`max_table_size = 4000`) — URL длиннее предела httpx | `DependencyUnavailable`, а не `httpx.InvalidURL`; `osrm_request_failed` с `error = InvalidURL`, `points = 4000` |
| `test_table_malformed_response` (параметризован: тело не JSON при `200`; `200 {code: Ok}` без `durations`; строк меньше, чем точек; `code` ≠ `Ok` при `200`; ячейка `Infinity`; ячейка `NaN`; целое вне диапазона `float`; `502` с текстовым телом; тело `200` глубже стека парсера JSON; ячейка времени в пути отрицательна; ячейка расстояния отрицательна; ячейка времени в пути больше суток; `null` в `durations`, но не в `distances` той же пары) | ответ графа, лог на уровне `debug` | `DependencyUnavailable`; одна запись `osrm_request_failed` с `duration_ms` и `error = malformed_response` (для `code` ≠ `Ok` — `error = <код>`, для `502` без JSON — `error = http_error`); записи `osrm_request_finished` нет — отвергнутый ответ не считается выполненным запросом |
| `test_graph_failure_does_not_affect_other_graphs` | граф `foot` отвечает `503`, граф `car` — `200` | `table(foot, …)` — `DependencyUnavailable`; следующий `table(car, …)` возвращает матрицу |

### Маршрут `route`

| Test | Scenario | Expected result |
|---|---|---|
| `test_route_found` | `route(car, [A, B, C])`, ответ `200 {code: Ok, routes: [{duration, distance, legs: [2 шт.], geometry: {type: LineString, coordinates: [[lon, lat], …]}}]}` | `Route` с `duration_s`, `distance_m`, двумя `legs` (`duration_s`, `distance_m`) и `geometry` — список `Point(lat, lon)`: координаты GeoJSON переставлены; запрос `GET /route/v1/car/…` с `overview=full`, `geometries=geojson`; `osrm_request_finished` с `endpoint = route`, `found = true` |
| `test_route_public_transport_is_car_times_factor` | `route(public_transport, [A, B])`, граф `car`: `duration 600`, leg `duration 600`, `distance 5000` | запрос ушёл в граф `car`; `duration_s == 900`, `legs[0].duration_s == 900`, расстояния и геометрия — без изменений |
| `test_route_no_route` | ответ `400 {code: NoRoute}` | `None` — не ошибка и не прямая; запись `osrm_request_finished` с `status = 400`, `found = false`; `osrm_request_failed` нет |
| `test_route_errors` (параметризован: `503`; `400 {code: NoSegment}`; `httpx.ConnectError`; `200` без `routes`; `200` без `geometry`; участков не на один меньше, чем точек; пустая геометрия; `duration = true`) | ответ графа, лог на уровне `debug` | `DependencyUnavailable(reason="osrm_unavailable")`; одна запись `osrm_request_failed` с `endpoint = route`, записи `osrm_request_finished` нет |
| `test_route_error_carries_no_coordinates` | геометрия с точкой вне диапазона широт (`95.43219`) | `DependencyUnavailable`; в тексте исключения и его цепочки (`traceback.format_exception`) нет координат отвергнутой точки |
| `test_route_needs_two_points` (параметризован: 0 и 1 точка) | `route(car, points)` | `ValueError` — ошибка вызывающего кода; запросов нет |

### Создание, закрытие, логи

| Test | Scenario | Expected result |
|---|---|---|
| `test_create_osrm_client_from_settings` | `create_osrm_client(settings)` с тремя URL, фактором и пределом | три `httpx.AsyncClient` с `base_url` из `osrm_url_car`, `osrm_url_foot`, `osrm_url_bike` и таймаутом из `osrm_timeout_s` (в тесте 45 с); фактор и предел — из настроек; сетевых вызовов нет; в окружении заданы `HTTP_PROXY` и `ALL_PROXY`, но клиенты их не используют (`trust_env=False`): координаты адресов не уходят на прокси |
| `test_aclose_closes_every_graph` | `aclose()` | закрыты все три HTTP-клиента |
| `test_logs_no_coordinates` | успешные и неуспешные `table` и `route` | ни в одной записи лога нет координат точек (ни чисел `lat`/`lon`, ни пути запроса) |

## `scripts/build_geocache.py` — сборка гео-кэша

Файл: `tests/scripts/test_build_geocache.py`.

> Замена стабами: HTTP — `httpx.MockTransport`, `sleep` — фейк. Исходные наборы и файл кэша —
> временные файлы.

| Test | Scenario | Expected result |
|---|---|---|
| `test_remote_town_not_stored` | адреса с районом `Домодедово` в исходном наборе и старая запись такого адреса в кэше | запросов по ним нет; в кэш не записаны, старая запись удалена |
| `test_next_variant_on_not_found` | первый вариант запроса не найден, второй найден | точка второго варианта записана |
| `test_refused_stops_requests` | первый же запрос получает `429` | больше запросов нет; оба адреса в списке ненайденных |
| `test_existing_entries_not_requested` | половина адресов уже в кэше | запросы только для отсутствующих; имеющиеся записи сохранены без изменений |
| `test_not_found_listed_and_exit_code` | один адрес не найден, один — ошибка сети | найденные записаны; оба ненайденных выведены списком и в кэш не записаны; код выхода не `0` |
| `test_all_found_exit_zero` | все адреса найдены | код выхода `0` |

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
| `test_bodyless_error_codes` (параметризован: `NotFound`→`404`, `Conflict`→`409`, `DependencyUnavailable`→`503`, `DatabaseFailure`→`500`, доменный наследник `PlanNotFound(NotFound)`→`404`) | роут поднимает исключение | код по таблице, тело пустое (`content == b""`), заголовка `Content-Type: application/json` нет, `X-Request-ID` есть |
| `test_unmapped_app_error_returns_500` | роут поднимает голый `AppError(reason="x")` (класса нет в таблице) | `500` без тела и запись `unhandled_error` — неописанная ошибка не превращается молча в `4xx` |
| `test_app_error_is_not_logged_by_handler` (параметризован: `NotFound`, `DatabaseFailure`) | роут поднимает исключение | в захваченных событиях нет записи от обработчика (ни `unhandled_error`, ни `request_validation_failed`): бизнес-ошибку логирует маршрут, обработчик только отвечает |

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
> контролируемым `connection()`), `OsrmClient` (реальный сетевой вызов не выполняется).

| Test | Scenario | Expected result |
|---|---|---|
| `test_get_db_connection_yields_and_releases` | фабрика вызвана как `Depends` с фейковым пулом в `app.state` | соединение из пула отдано генератором и возвращено в пул после выхода из блока |
| `test_get_db_connection_pool_not_opened_at_import` | создание пула (`open=False`), `pool.open()` не вызывается | конструктор пула не выполняет сетевого подключения — приложение поднимается без доступной БД |
| `test_get_osrm_client_returns_shared_client` | фабрика вызвана как `Depends`, клиент уже создан в `lifespan` и лежит в `app.state.osrm_client` | возвращает тот же объект `OsrmClient`, не создаёт новый |
| `test_get_osrm_client_not_closed_per_request` | выход из генератора после одного вызова зависимости | `aclose()` `OsrmClient` НЕ вызывается — клиент общий на всё приложение, закрывается только в `lifespan`-shutdown (переоткрытие TCP-соединения на каждый запрос убило бы смысл `keep-alive` к OSRM) |

## `src/app.py` — app factory и lifespan

> Замена стабами: конструктор пула БД и `create_osrm_client` (проверяем, что
> `lifespan` их вызывает и потом закрывает, а не что они реально открывают соединения).

| Test | Scenario | Expected result |
|---|---|---|
| `test_lifespan_creates_and_opens_db_pool_without_waiting` | приложение поднято через `lifespan` (`asgi-lifespan`/`TestClient`) | `app.state.db_pool` создан, `pool.open(wait=False)` вызван один раз — старт не блокируется недоступностью БД |
| `test_lifespan_creates_osrm_client` | запуск `lifespan` | `app.state.osrm_client` — `OsrmClient`, собранный `create_osrm_client(settings)`; сетевых вызовов при старте нет — backend поднимается, пока графы OSRM ещё строятся |
| `test_lifespan_closes_pool_and_client_on_shutdown` | завершение `lifespan` | `pool.close()` и `osrm_client.aclose()` вызваны по одному разу |
| `test_lifespan_closes_pool_when_data_files_fail` | сборка загрузчика и сервиса списков при старте поднимает ошибку (битый файл конфигурации) | старт падает с этой ошибкой; пул БД и HTTP-клиент OSRM закрыты |
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

## `api` — GET /api/v1/regions

Файл: `tests/api/test_regions.py`.

> Замена стабами: сервис списков — фейк через `app.dependency_overrides`, который возвращает
> заданные регионы; БД нет.

| Test | Scenario | Expected result |
|---|---|---|
| `test_list_regions` | сервис вернул `east`/«Восток», `south_east`/«Юго-Восток» | `200`, тело `[{"code": "east", "name": "Восток"}, {"code": "south_east", "name": "Юго-Восток"}]` в том же порядке; есть `X-Request-ID` |

## `api` — GET /api/v1/engineers

Файл: `tests/api/test_engineers.py`.

> Замена стабами: сервис списков — фейк через `app.dependency_overrides`, который возвращает
> заданные бригады или поднимает заданное исключение и запоминает вызовы; БД нет. Логи —
> разбором JSON-строк stderr (`capsys`, `tests/log_records.py`).

| Test | Scenario | Expected result |
|---|---|---|
| `test_list_engineers` | `?region=east`; сервис вернул бригаду: смена `10:00`–`23:30`, старт `(55.72, 37.74)`, навыки `connection`, `emergency`, транспорт `car` | `200`, `[{"id", "name", "vehicle_type": "car", "skills": ["connection", "emergency"], "shift_start": "10:00", "shift_end": "23:30", "start": {"lat": 55.72, "lon": 37.74}}]`; сервис вызван с `east` |
| `test_list_engineers_empty` | сервис вернул `[]` | `200`, `[]` |
| `test_list_engineers_region_invalid` (параметризован: нет параметра, `East!`, 51 символ) | запрос с таким `region` | `400`, `{"fields": [{"name": "region", ...}]}`; сервис не вызван |
| `test_list_engineers_unknown_region` | сервис поднимает `InvalidInput(reason="unknown_region", fields=[("region", "Неизвестный регион")])` | `400`, `{"fields": [{"name": "region", "message": "Неизвестный регион"}]}`; запись `list_engineers_failed` уровня `warning` с `reason = unknown_region`, `region` и `request_id` ответа |
| `test_list_engineers_db_unavailable` | сервис поднимает `DependencyUnavailable(reason="db_unavailable")` | `503` без тела; запись `list_engineers_failed` уровня `error` |
| `test_list_engineers_db_failure` | сервис поднимает `DatabaseFailure` | `500` без тела |

## `api` — GET /api/v1/tickets

Файл: `tests/api/test_tickets.py`.

> Замена стабами: как в разделе `GET /api/v1/engineers`.

| Test | Scenario | Expected result |
|---|---|---|
| `test_list_tickets` | `?region=east`; сервис вернул заявку без `Тип заявки BK`, района и требуемого транспорта, окно `2026-08-17 10:00`–`12:00` | `200`, заявка со всеми полями контракта: `location: {"lat", "lon"}`, `window_start: "2026-08-17T10:00:00"`, `window_end: "2026-08-17T12:00:00"`, `received_at: "2026-08-17T00:00:00"`, `priority` — число, `type_bk`, `district`, `required_vehicle` — `null`; назначений бригадам в заявке нет |
| `test_list_tickets_empty` | сервис вернул `[]` | `200`, `[]` |
| `test_list_tickets_region_invalid` (параметризован: нет параметра, `East!`, 51 символ) | запрос с таким `region` | `400`, `fields` с `region`; сервис не вызван |
| `test_list_tickets_plan_id_ignored` | `?region=east&plan_id=1` | `200`, параметр `plan_id` не влияет на ответ: в контракте его нет |
| `test_list_tickets_unknown_region` | сервис поднимает `InvalidInput` про регион | `400`, `fields` с `region`; запись `list_tickets_failed` уровня `warning` |
| `test_list_tickets_db_unavailable` | сервис поднимает `DependencyUnavailable` | `503` без тела; запись `list_tickets_failed` уровня `error` |
| `test_list_tickets_db_failure` | сервис поднимает `DatabaseFailure` | `500` без тела |

## `api` — PATCH /api/v1/tickets/{ticket_id}/status

Файл: `tests/api/test_ticket_status.py`.

> Замена стабами: сервис статусов — фейк через `app.dependency_overrides`, который возвращает
> заявку с запрошенным статусом или поднимает заданное исключение и запоминает вызовы; БД нет.
> Логи — разбором JSON-строк stderr (`capsys`, `tests/log_records.py`). Предел тела в тесте на
> `413` — `Settings(max_request_body_bytes=1024)`.

| Test | Scenario | Expected result |
|---|---|---|
| `test_change_ticket_status` | `PATCH /api/v1/tickets/87/status` с `{"status": "completed"}` | сервис вызван с `(87, completed)`; `200`, заявка со всеми полями контракта `Ticket` и `"status": "completed"` |
| `test_change_ticket_status_body_invalid` (параметризован: `{}`, `{"status": "done"}`, `{"status": null}`, лишнее поле `{"status": "completed", "comment": "x"}`) | запрос с таким телом | `400`, `{"fields": [{"name": "status" \| "comment", ...}]}`; сервис не вызван |
| `test_change_ticket_status_body_not_json` | тело `status=completed` | `400` с `message`; сервис не вызван |
| `test_change_ticket_status_id_invalid` (параметризован: `0`, `-1`, `abc`, `9223372036854775808`) | запрос с таким `ticket_id` | `400`, `{"fields": [{"name": "ticket_id", ...}]}`; сервис не вызван |
| `test_change_ticket_status_transition_not_allowed` | сервис поднимает `InvalidInput(reason="transition_not_allowed", message=...)` с `params` `ticket_id`, `status_from`, `status_to` | `400`, `{"message": "Статус заявки нельзя изменить с «Выполнена» на «В пути»"}`; запись `ticket_status_change_failed` уровня `warning` с `reason`, `ticket_id`, `status_from`, `status_to` и `request_id` ответа |
| `test_change_ticket_status_not_found` | сервис поднимает `NotFound(reason="ticket_not_found")` | `404` без тела; запись `ticket_status_change_failed` уровня `warning` с `reason = ticket_not_found` и `ticket_id` |
| `test_change_ticket_status_db_unavailable` | сервис поднимает `DependencyUnavailable(reason="db_unavailable")` | `503` без тела; запись `ticket_status_change_failed` уровня `error` |
| `test_change_ticket_status_db_failure` | сервис поднимает `DatabaseFailure` | `500` без тела |
| `test_change_ticket_status_too_large` | тело больше предела 1024 байта | `413` без тела; сервис не вызван |
| `test_ticket_status_get_not_implemented` | `GET /api/v1/tickets/87/status` | `501` без тела (метода нет у операции); сервис не вызван |

## `api` — POST /api/v1/plan/build, GET /api/v1/plan/{plan_id}, GET /api/v1/plan/{plan_id}/compare

Файл: `tests/api/test_plan.py`.

> Замена стабами: `PlanBuilder`/`PlanReader` — фейки через `app.dependency_overrides`
> (`FakePlanBuilder`/`FakePlanReader` в `tests/api/region_fakes.py`), которые запоминают
> вызовы (включая `compare`) и возвращают заданный результат или поднимают заданное
> исключение; БД, OSRM и солвер не участвуют. `background_tasks.add_task` в `TestClient`
> выполняется до возврата ответа клиенту, так что `build_calls` фейка проверяется сразу
> после запроса.

| Test | Scenario | Expected result |
|---|---|---|
| `test_build_plan_returns_202_running` | валидный запрос | `202`, тело `Plan` со `status=running` и без `engineers`/`unassigned`; `enqueue` вызван с `(region, plan_date, algorithm)`; фоновая задача `build` поставлена с `plan_id`, теми же `tickets`/`engineers`, что вернул `enqueue`, `plan_date` и `algorithm` |
| `test_build_plan_invalid_date` | `plan_date="2026-02-30"` (несуществующая дата, форму регулярное выражение спеки принимает) | `400`, `{"fields": [{"name": "plan_date", "message": "Несуществующая дата"}]}` |
| `test_build_plan_rejects_malformed_body` (параметризован: пустое тело, без `algorithm`, `algorithm` вне перечня, лишнее поле) | запрос с таким телом | `400` |
| `test_build_plan_unknown_region` | `enqueue` поднимает `InvalidInput(reason="unknown_region", fields=...)` | `400`, `{"fields": [{"name": "region", ...}]}`; фоновая задача не ставится |
| `test_build_plan_dependency_failure` (параметризован: `DependencyUnavailable`, `DatabaseFailure`) | `enqueue` поднимает эту ошибку | `503` \| `500` без тела |
| `test_get_running_plan` | `PlanRead(status="running", ...)` | `200`, `engineers`/`unassigned`/`failed_reason` — `null` |
| `test_get_failed_plan` | `PlanRead(status="failed", failed_reason=...)` | `200`, тот же `failed_reason`; `engineers`/`unassigned` — `null` |
| `test_get_done_plan` | `PlanRead(status="done", ...)` с одной бригадой и одним визитом, одной неназначенной заявкой, заполненным `metrics` | `200`, тело `Plan` с `engineers`/`unassigned`/`metrics`, все поля контракта (`Visit`, `EngineerRoute`, `UnassignedTicket`, `PlanMetrics`) заполнены как в `PlanRead` |
| `test_get_plan_not_found` | `reader.get` поднимает `NotFound` | `404` без тела |
| `test_get_plan_invalid_id` | `plan_id=0` | `400` |
| `test_get_plan_dependency_failure` (параметризован: `DependencyUnavailable`, `DatabaseFailure`) | `reader.get` поднимает эту ошибку | `503` \| `500` без тела |
| `test_build_and_get_failed_events_logged` | `enqueue`/`reader.get` поднимают `InvalidInput`/`NotFound` | записи `plan_build_failed`/`plan_get_failed` уровня `warning` с `reason` |
| `test_compare_plan_returns_entries` | `reader.compare` возвращает 2 записи (`engineers_used`, `total_distance_km`) | `200`, тело — массив `PlanComparisonEntry` в том же порядке, поля `metric`/`main`/`baseline`/`delta` как вернул сервис |
| `test_compare_plan_invalid_ids` (параметризован: `plan_id=0`, `baseline_plan_id=0`) | путь или query-параметр вне 1..2^63−1 | `400` |
| `test_compare_plan_missing_baseline_query` | запрос без `baseline_plan_id` | `400` |
| `test_compare_plan_not_found` | `reader.compare` поднимает `NotFound` | `404` без тела |
| `test_compare_plan_not_ready` | `reader.compare` поднимает `InvalidInput(reason="plan_not_ready", message=...)` | `400`, `{"message": ...}` |
| `test_compare_plan_dependency_failure` (параметризован: `DependencyUnavailable`, `DatabaseFailure`) | `reader.compare` поднимает эту ошибку | `503` \| `500` без тела |
| `test_compare_plan_failed_logged` | `reader.compare` поднимает `NotFound`/`InvalidInput` | запись `plan_compare_failed` уровня `warning` с `reason`, `plan_id`, `baseline_plan_id` |

## `api` — POST /api/v1/data/upload, POST /api/v1/data/demo

Файл: `tests/api/test_data.py`.

> Замена стабами: загрузчик — фейк через `app.dependency_overrides`, который возвращает
> заданный итог загрузки или поднимает заданное исключение и запоминает аргументы вызова
> (код региона, источник, байты файла); БД и геокодера нет. Логи — разбором JSON-строк
> stderr (`capsys`, `tests/log_records.py`). Предел тела в тестах на `413` —
> `Settings(max_request_body_bytes=1024)`.

| Test | Scenario | Expected result |
|---|---|---|
| `test_upload_csv` | multipart: `region=east`, `tickets_file` с именем `tickets.CSV`; загрузчик вернул итог с одной невалидной строкой | загрузчик вызван с `("east", "csv", байты файла)`; `200`, `{"region": "east", "engineers", "tickets", "rows_total", "rows_skipped", "rows_invalid": [{"row": 5, "reason": "bad_datetime", "column": "Начало"}]}` |
| `test_upload_json` | то же с файлом `tickets.json` | загрузчик вызван с источником `json`; `200` |
| `test_upload_invalid_row_without_column` | загрузчик вернул невалидную строку с `column = None` (контракт допускает ошибку, не привязанную к колонке) | в ответе `"column": null`, ответ проходит схему `InvalidRow` |
| `test_upload_bad_extension` (параметризован: `tickets.xlsx`, `tickets`, `tickets.csv.txt`) | multipart с таким именем файла | `400`, `{"fields": [{"name": "tickets_file", "message": "Файл должен быть .csv или .json"}]}`; загрузчик не вызван; запись `data_upload_failed` уровня `warning` с `reason = file_type_invalid` и `region`, без имени файла |
| `test_upload_form_invalid` (параметризован: нет `tickets_file`, нет `region`, `region=East!`, лишнее поле формы `engineers_file`) | multipart с таким составом | `400`, `fields` с именем параметра формы; загрузчик не вызван |
| `test_upload_broken_multipart` | тело `multipart/form-data` с испорченным заголовком части (символ `\r` внутри заголовка) | `400` с `message`, как у любого неразбираемого тела, а не `500`; загрузчик не вызван; запись `data_upload_failed` уровня `warning` с `reason = form_invalid` |
| `test_upload_form_over_limits` | три файла в форме при пределе два | `400` с `message` (отказ Starlette); загрузчик не вызван; запись `data_upload_failed` с `reason = form_invalid` |
| `test_upload_too_large` | файл 2000 байт при пределе 1024, с `Content-Length` | `413` без тела; загрузчик не вызван; записи `data_upload_failed` нет |
| `test_upload_too_large_without_content_length` | то же тело чанками, без `Content-Length` | `413` без тела (предел срабатывает при чтении формы); загрузчик не вызван; записи `data_upload_failed` нет — `413` не считается отказом разбора формы |
| `test_demo_load` | `POST /api/v1/data/demo` с телом `{"region": "east"}` | загрузчик вызван с `("east", "demo")` без файла; `200`, итог загрузки |
| `test_demo_body_invalid` (параметризован: `{}`, `{"region": "East!"}`, `region` из 51 символа, лишнее поле `{"region": "east", "date": "2026-08-17"}`) | `POST /api/v1/data/demo` с таким телом | `400`, `fields` с именем поля (`region` или лишнего); загрузчик не вызван |
| `test_demo_body_not_json` | тело `region=east` (не JSON) | `400` с `message`; загрузчик не вызван |
| `test_demo_region_in_query_not_accepted` | `POST /api/v1/data/demo?region=east` без тела | `400`: регион берётся только из тела; загрузчик не вызван |
| `test_demo_too_large` | тело больше предела 1024 байта | `413` без тела; загрузчик не вызван |
| `test_demo_get_does_not_load` | `GET /api/v1/data/demo?region=east` | `501` без тела (метода нет у операции); загрузчик не вызван |
| `test_load_errors_map_to_status` (параметризован: upload и demo × `InvalidInput` с `fields` региона, `InvalidInput` с `message`, `DependencyUnavailable`, `DatabaseFailure`) | загрузчик поднимает исключение | `400 {"fields": [{"name": "region", ...}]}`, `400 {"message": ...}`, `503` без тела, `500` без тела соответственно; записей `data_upload_failed` нет — ошибку загрузки логирует загрузчик |

## `api` — заглушка /api/v1/{path}

Файл: `tests/api/test_not_implemented.py`.

> Зависимостей нет: заглушка не использует `Depends` на БД/OSRM, стабы не нужны.
> Порядок регистрации проверяется на отдельном `FastAPI()` с тестовым роутом
> `GET /api/v1/regions`, объявленным до заглушки; в самом приложении — на путях операций,
> которых ещё нет в контракте (`/api/v1/plan/...`).

| Test | Scenario | Expected result |
|---|---|---|
| `test_unimplemented_path_returns_501_without_body` | `GET /api/v1/plan/1` на `create_app()` | `501`, тело пустое (`content == b""`), заголовка `Content-Type: application/json` нет |
| `test_stub_answers_any_method` (параметризован: `GET`, `POST`, `PATCH`, `DELETE`) | запрос методом на `/api/v1/plan/1/replan` | `501`, тело пустое |
| `test_stub_answers_nested_and_root_paths` (параметризован: `/api/v1/`, `/api/v1/tickets/42/status`) | `GET` по пути | `501`, тело пустое — заглушка ловит путь любой глубины под префиксом |
| `test_implemented_route_takes_precedence_over_stub` | на `FastAPI()` подключён роутер с `GET /api/v1/regions` → `200 []`, затем заглушка; запросы `GET /api/v1/regions` и `GET /api/v1/engineers` | первый — `200 []` от роута, второй — `501` от заглушки |
| `test_wrong_method_on_implemented_path_returns_501` | тот же `FastAPI()` с `GET /api/v1/regions` и заглушкой; `POST /api/v1/regions` | `501` без тела, а не `405`: полное совпадение пути и метода даёт заглушка |
| `test_path_outside_api_prefix_returns_404` | `GET /unknown` и `GET /api/v2/regions` | `404`: заглушка ограничена префиксом `/api/v1` |
| `test_health_is_not_shadowed_by_stub` | `GET /health` на `create_app()` | `200` от health-роута |
| `test_stub_is_absent_from_openapi_schema` | `create_app().openapi()` | в `paths` нет пути `/api/v1/{path}` — заглушка не часть контракта и не попадает в контрактные тесты; пути `/api/v1` в схеме — ровно операции спеки |
| `test_stub_request_is_logged_with_request_id` | `GET /api/v1/plan/1` на `create_app()` (JSON на stderr, `capsys`) | ответ содержит `X-Request-ID`; в логе событие `http_request_finished` со `status=501`, `path="/api/v1/{path:path}"` (шаблон, а не запрошенный путь) и тем же `request_id` |

## `src/api/schemas/generated/common.py` — LocalDateTime, LocalTime

> Мок не нужен: проверка сгенерированной по `specs/common.yaml` модели (`make gen-api`) —
> она же будет разбирать время во входных параметрах операций.

| Test | Scenario | Expected result |
|---|---|---|
| `test_local_datetime_accepts_local_time` | `"2026-09-23T13:20:00"` | принято, значение не изменено |
| `test_local_datetime_rejects_zone` | `"2026-09-23T13:20:00Z"`, `"2026-09-23T13:20:00+03:00"` | `pydantic.ValidationError` — время с поясом не принимается |
| `test_local_datetime_rejects_other_forms` | `"2026-09-23T13:20:00.5"`, `"2026-09-23 13:20:00"`, `"2026-09-23T13:20"`, `""` | `pydantic.ValidationError` |
| `test_local_time_accepts_hours_minutes` | `"00:00"`, `"13:20"`, `"23:59"` | принято, значение не изменено |
| `test_local_time_rejects_other_forms` | `"13:20:00"`, `"9:05"`, `"24:00"`, `"12:60"`, `"13:20+03:00"`, `""` | `pydantic.ValidationError` — только `ЧЧ:ММ` без секунд и пояса |
| `test_local_datetime_rejects_out_of_range` | `"2026-13-01T10:00:00"`, `"2026-09-32T10:00:00"`, `"2026-09-23T24:00:00"`, `"2026-09-23T10:60:00"` | `pydantic.ValidationError` — месяц, день, час и минута вне допустимых диапазонов |

## Стенд Docker Compose — smoke

> Ручной сценарий из корневого `README.md`, не часть `pytest`: поднимает настоящие
> контейнеры (`db`, `osrm-prepare`, `osrm-car`, `osrm-foot`, `osrm-bike`, `backend`, `frontend`), ничего не мокается.
> Запросы идут через nginx фронтенда (`http://localhost:8080`).

| Test | Scenario | Expected result |
|---|---|---|
| `smoke_compose_up` | `cp .env.example .env && docker compose up -d` на чистой машине | `db` и `backend` — `healthy`, `frontend` отвечает; `osrm-prepare` готовит графы `car`, `foot`, `bike` или сразу завершается, если они уже есть в volume; `osrm-car`, `osrm-foot`, `osrm-bike` стартуют после него |
| `smoke_health_via_proxy` | `curl -i http://localhost:8080/health` | `200`, `{"status": "ok", ...}` — отвечает и пока `osrm-prepare` ещё работает |
| `smoke_unimplemented_via_proxy` | `curl -i http://localhost:8080/api/v1/plan/1` | `501`, тело пустое, есть заголовок `X-Request-ID` |
| `smoke_regions_via_proxy` | `curl -i http://localhost:8080/api/v1/regions` | `200`, три региона: `east`, `south_east`, `south_center` с названиями |
| `smoke_demo_load_via_proxy` | `curl -X POST -H 'Content-Type: application/json' -d '{"region": "east"}' http://localhost:8080/api/v1/data/demo`, затем `GET /api/v1/engineers?region=east` и `GET /api/v1/tickets?region=east`; `POST` демо-набора повторно и снова `GET /api/v1/engineers?region=east` | `200` с итогом загрузки, `rows_invalid` пустой; 13 бригад и все заявки демо-набора региона; после повторной загрузки у бригад те же `id` |
| `smoke_upload_via_proxy` | `curl -F region=south_east -F tickets_file=@"docs/synthetic_data/<файл Юго-Востока>.csv" http://localhost:8080/api/v1/data/upload` | `200`; файл исходного набора загружен без правок, `rows_skipped` — пустые строки и служебная строка офиса |
| `smoke_body_limit_via_proxy` | `POST /api/v1/data/upload` с телом больше `MAX_REQUEST_BODY_BYTES` | `413` от nginx, запрос не доходит до backend (в `docker compose logs backend` нет записи о нём) |
| `smoke_backend_logs_are_json` | `docker compose logs --no-log-prefix backend` | каждая строка — один JSON-объект; у записи `http_request_finished` есть `request_id` |
| `smoke_spa_fallback` | `curl -i http://localhost:8080/plan/1` (клиентский маршрут React) | `200`, отдаётся `index.html` |
| `smoke_backend_migrates_on_start` | `make up` на volume БД, оставшемся от прежнего запуска стенда; `docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt'` | `migrate` — `Exited (0)`, в `docker compose logs migrate` JSON-записи о применении ревизий `5d23f2956ce7` и `cb3db41d521a` (на volume, где первая уже применена, — только о второй); `backend` стартует после него и становится `healthy`; в БД шесть таблиц и `alembic_version` |
| `smoke_restart_does_not_migrate_again` | повторный `make up` | `migrate` снова `Exited (0)`, в его логе нет записи о применении ревизии; `backend` `healthy` |
| `smoke_backend_connects_as_app_rw` | `docker compose exec db psql … -c "SELECT DISTINCT usename FROM pg_stat_activity WHERE datname = current_database() AND backend_type = 'client backend' AND pid <> pg_backend_pid()"` | соединения пула приложения — под `app_rw`, не под владельцем схемы |
| `smoke_backend_has_no_owner_credentials` | `docker compose exec backend env` | нет ни `MIGRATION_DATABASE_URL`, ни `APP_RW_PASSWORD`, ни `APP_RO_PASSWORD`; `POSTGRES_PASSWORD` тоже нет — в `DATABASE_URL` только пароль `app_rw` |
| `smoke_db_port_on_loopback` | `docker compose port db 5432`; с хоста `psql -h 127.0.0.1 -p "$DB_PORT" -U app_ro -d "$POSTGRES_DB" -c 'SELECT count(*) FROM regions'` | порт опубликован только на `127.0.0.1:${DB_PORT}`; `app_ro` читает, запись под ним отклоняется правами |
| `smoke_backend_local_time` | `docker compose exec backend python -c "import time; print(time.strftime('%z'))"` | `+0300`; метки `timestamp` в логе `backend` совпадают с местным временем, а не с UTC |
| `smoke_migration_failure_blocks_backend` | в `.env` временно другой `POSTGRES_PASSWORD` (в томе БД остаётся прежний); `docker compose up -d` | `migrate` — `Exited (1)`, последняя строка его лога — JSON `migration_failed`; `docker compose up` завершается ошибкой «service "migrate" didn't complete successfully»; остановленный `backend` не стартует, уже запущенный с неизменёнными настройками продолжает работать; после возврата значения `make up` поднимает стенд |
| `smoke_osrm_prepare_reuses_graphs` | повторный `make up` после готовых графов; `docker compose logs --tail 5 osrm-prepare` | `osrm-prepare` — `Exited (0)`, в логе «graph is up to date» для каждого из трёх профилей, строк `extracting` нет — графы не пересобираются |
| `smoke_osrm_prepare_rebuilds_on_new_extract` | `osrm/moscow-oblast.osm.pbf` заменён другим файлом; `make up` | в логе `osrm-prepare` — `extracting`, `partitioning`, `customizing` для `car`, `foot`, `bike` и `done`; `osrm-car`, `osrm-foot`, `osrm-bike` перезапущены и отвечают на `/route` |
| `smoke_osrm_prepare_resumes_interrupted_build` | во время `foot: extracting` — `docker compose kill osrm-prepare`; затем `make up` | `car` — «graph is up to date», `foot` и `bike` собираются заново; стенд поднимается |
| `smoke_osrm_prepare_keeps_graphs_without_extract` | готовые графы; `docker compose run --rm --no-deps -v <пустой каталог>:/src:ro osrm-prepare` | сервис завершается ошибкой `cp: can't stat '/src/moscow-oblast.osm.pbf'`; в volume `osrm-data` папки `car`, `foot`, `bike` и их `ready` на месте; следующий `make up` — «graph is up to date» для всех трёх |
| `smoke_osrm_profiles_differ` | из контейнера `backend`: `OsrmClient.route` по одним и тем же двум точкам в Москве (~5 км) для `car`, `bike`, `foot`, `public_transport` | у всех четырёх маршрут найден; время `foot` > `bike` > `car`; время `public_transport` = время `car` × 1,5 |
| `smoke_osrm_table_over_default_limit` | из контейнера `backend`: `OsrmClient.table(car, …)` по 150 точкам внутри МКАД | матрица 150 × 150 без `None` на диагонали и без ошибки — `--max-table-size 1000` действует (предел `osrm-routed` по умолчанию — 100) |
| `smoke_env_example_has_role_passwords` | `.env` без `APP_RW_PASSWORD`; `docker compose up -d` | compose отказывается стартовать и называет переменную; в `.env.example` обе переменные паролей ролей есть |

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
| `make_gen_api_generates_common_schemas` | `make gen-api` | в `back/src/api/schemas/generated/` есть модели и из `specs/openapi.yaml` (`HealthStatus`), и из `specs/common.yaml` (`LocalDateTime`, `ValidationError`, `RequestMessage`, `FieldErrors`, `FieldError`) — каждая спека своим запуском генератора, в свой модуль |
| `make_up_then_smoke_passes` | нет `.env`: `make up && make smoke` | `.env` создан из `.env.example` (существующий `make up` не трогает), образы пересобраны, стенд поднят; `smoke` печатает `200` для `/health` и `200` для `/api/v1/regions` через фронтенд-прокси на `FRONTEND_PORT` из `.env`, код `0` |
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
> растёт вместе со спекой. Загрузчик, сервис списков, построитель и читатель плана заменены
> через `app.dependency_overrides` фейками, которые возвращают валидный по контракту
> результат (итог загрузки с невалидной строкой, одна бригада, одна заявка; смена статуса —
> заявка с запрошенным статусом; построение плана — план в очереди с той же бригадой и
> заявкой; чтение плана — план `done` без маршрутов и неназначенных), а на неизвестный
> регион поднимают `InvalidInput` — так позитивные кейсы проверяют форму успешных ответов
> без БД. Чтение плана возвращает `metrics`, заполненный по той же схеме, что и
> `engineers`/`unassigned`; сравнение планов (`compare`) возвращает фиксированный список из
> двух корректных записей независимо от переданных `plan_id`/`baseline_plan_id`.

| Test | Scenario | Expected result |
|---|---|---|
| `test_api_conforms_to_openapi_schema` | `schemathesis.from_path("specs/openapi.yaml")` с методами генерации positive + negative, все операции спеки | каждый сгенерированный кейс: код ответа объявлен у операции, тело соответствует схеме (у кодов без тела — пустое), заголовок `X-Request-ID` есть; запрос, нарушающий ограничение спеки, получает `400`, а не `422` |
