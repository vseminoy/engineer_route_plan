# Тесты backend (`back/`)

## Содержание

- [`src/config.py` — Settings](#srcconfigpy--settings)
- [`src/logging.py` — логирование с run_id](#srcloggingpy--логирование-с-run_id)
- [`src/errors.py` — доменные исключения](#srcerrorspy--доменные-исключения)
- [`alembic/versions/5d23f2956ce7_initial_schema.py` — схема БД](#alembicversions5d23f2956ce7_initial_schemapy--схема-бд)
- [`alembic/env.py` — запуск миграций](#alembicenvpy--запуск-миграций)
- [`src/repository/db.py` — обёртка запросов к БД](#srcrepositorydbpy--обёртка-запросов-к-бд)
- [`src/repository/region_data.py` — замена данных региона](#srcrepositoryregion_datapy--замена-данных-региона)
- [`src/service/ticket_file.py` — чтение файла заявок](#srcserviceticket_filepy--чтение-файла-заявок)
- [`src/service/ticket_types.py` — таблица соответствия типов заявок](#srcserviceticket_typespy--таблица-соответствия-типов-заявок)
- [`src/service/regions.py` — конфигурация регионов](#srcserviceregionspy--конфигурация-регионов)
- [`src/service/engineers_generator.py` — генератор демо-бригад](#srcserviceengineers_generatorpy--генератор-демо-бригад)
- [`src/service/geocoding.py` — координаты адресов](#srcservicegeocodingpy--координаты-адресов)
- [`src/service/loader.py` — загрузка данных региона](#srcserviceloaderpy--загрузка-данных-региона)
- [`src/clients/nominatim.py` — клиент Nominatim](#srcclientsnominatimpy--клиент-nominatim)
- [`scripts/build_geocache.py` — сборка гео-кэша](#scriptsbuild_geocachepy--сборка-гео-кэша)
- [`src/api/errors.py` — единый обработчик ошибок](#srcapierrorspy--единый-обработчик-ошибок)
- [`src/api/body_limit.py` — предел размера тела запроса](#srcapibody_limitpy--предел-размера-тела-запроса)
- [`src/api/deps.py` — Depends-фабрики БД/OSRM](#srcapidepspy--depends-фабрики-бдosrm)
- [`src/app.py` — app factory и lifespan](#srcapppy--app-factory-и-lifespan)
- [`api` — GET /health](#api--get-health)
- [`api` — заглушка /api/v1/{path}](#api--заглушка-apiv1path)
- [`src/api/schemas/generated/common.py` — LocalDateTime](#srcapischemasgeneratedcommonpy--localdatetime)
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
| `test_migration_settings_reads_from_env` | заданы `MIGRATION_DATABASE_URL`, `LOG_LEVEL`, `LOG_FORMAT` | `MigrationSettings()` собирает поля с этими значениями; `DATABASE_URL` и `OSRM_URL` ему не нужны |
| `test_migration_settings_missing_url` | `MIGRATION_DATABASE_URL` не задан | `pydantic.ValidationError` |
| `test_migration_settings_ignore_env_file` | в текущем каталоге `.env` с `MIGRATION_DATABASE_URL`, в окружении его нет | `pydantic.ValidationError`: адрес владельца схемы берётся только из окружения процесса миграции, не из `.env` приложения |
| `test_settings_ignore_migration_vars_in_env` | в окружении `MIGRATION_DATABASE_URL`, `APP_RW_PASSWORD`, `APP_RO_PASSWORD` рядом с обычными переменными | `Settings()` собирается, этих полей у него нет — приложение не получает адрес владельца схемы |
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
| `test_upgrade_creates_schema` | `upgrade head` на пустой БД | таблицы `regions`, `engineers`, `tickets`, `plans`, `assignments`, `replan_events`; `alembic_version` = `5d23f2956ce7`; роли `app_rw` и `app_ro` существуют и могут входить |
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

## `alembic/env.py` — запуск миграций

> Мока нет: `@pytest.mark.integration`, контейнер PostGIS как в предыдущем разделе.
> Команда запускается отдельным процессом (`python -m alembic upgrade head` из `back/`) с
> явно собранным окружением — так же, как её запускает сервис `migrate` стенда.

| Test | Scenario | Expected result |
|---|---|---|
| `test_env_uses_migration_url` | в окружении `MIGRATION_DATABASE_URL` на контейнер, `DATABASE_URL` нет, `sqlalchemy.url` в `alembic.ini` пуст | код `0`, ревизия применена |
| `test_env_accepts_plain_postgresql_url` | `MIGRATION_DATABASE_URL` в виде `postgresql://…` (как на стенде, без имени драйвера) | код `0`: драйвер `psycopg` подставляет сам `env.py` |
| `test_env_logs_are_json` | `LOG_FORMAT=json`; `upgrade head` на пустой БД | каждая строка вывода — один JSON-объект; есть запись о применении ревизии `5d23f2956ce7`; паролей ролей и адреса БД с паролем в выводе нет |
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
| `test_replace_inserts_region_engineers_tickets` | пустая БД; регион `east`, 2 бригады, 3 заявки | возвращён `id` региона; в БД 1 регион, 2 бригады и 3 заявки этого региона; точки, смены, навыки, окна и `received_at` прочитаны обратно без изменений (время — наивное, как передано) |
| `test_replace_same_code_keeps_region_id` | регион `east` загружен дважды с разным названием и офисом | тот же `id`; название, адрес и точка офиса — из второй загрузки |
| `test_replace_removes_previous_region_data` | у региона есть бригады, заявки, два плана (второй — потомок первого), строки плана и событие перепланирования; загрузка нового набора | прежних бригад, заявок, планов, строк планов и событий региона нет; в БД только новый набор |
| `test_replace_keeps_other_regions` | загружены `east` и `south_east`, затем `east` загружен повторно | данные `south_east` не изменились |
| `test_replace_duplicate_external_id_loads_both` | две заявки с одинаковым `external_id` | обе вставлены, у каждой свой `id` |
| `test_replace_constraint_violation_rolls_back` | у региона уже есть данные; новый набор содержит бригаду с 4 навыками | поднято `DatabaseFailure(reason="db_query_failed")`, причина — нарушение `ck_engineers__skills`; запись `db_query_failed`; прежние данные региона на месте, новых нет |
| `test_replace_overnight_shift_rolls_back` | бригада со сменой `22:00–06:00` | `DatabaseFailure`, нарушение `ck_engineers__shift_order`; прежние данные на месте |

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
| `test_json_invalid_syntax` | обрезанный JSON | `InvalidInput(reason="file_format_invalid")` |
| `test_unparsable_file_is_format_error` | поле CSV длиннее предела библиотеки `csv` (200 000 символов); JSON из 200 000 `[`; JSON с числом из 5000 цифр | `InvalidInput(reason="file_format_invalid")`, а не необработанное исключение (`500`) |
| `test_json_bad_value_in_known_column` | в JSON значение «Адрес» — вложенный объект | `InvalidInput(reason="file_format_invalid")`, `message` называет колонку |
| `test_unknown_columns_dropped` | JSON с ключом из 1000 символов (вложенный объект) и `Бригада`; CSV с колонками `Подключение` и `Бригада` | в строке только колонки, которые использует загрузчик; неизвестный ключ с вложенным объектом не ошибка |
| `test_too_many_columns` | заголовок CSV из 20 005 колонок и 1000 пустых строк | `InvalidInput(reason="file_format_invalid")` быстрее 100 мс |
| `test_too_many_rows` | CSV и JSON из 10 001 строки; CSV из 10 000 строк | `InvalidInput(reason="too_many_rows")` для 10 001; 10 000 строк разобраны |
| `test_blank_rows_skipped` | две пустые строки и строка из одних `;` между заявками | не заявки, `rows_skipped = 3`, в `rows_invalid` не попали |
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
| `test_load_csv` | CSV региона `east`: 3 заявки, 2 пустые строки, служебная строка, 1 невалидная строка | в репозиторий переданы регион `east` с офисом из служебной строки, бригады генератора и 3 заявки; итог: `rows_total = 7`, `rows_skipped = 3`, `rows_invalid = 1` с номером строки и причиной; запись `data_load_finished` с `source = csv`, `region`, `rows_total`, `rows_skipped`, `rows_invalid`, `invalid_by_reason = {"bad_datetime": 1}`, `engineers`, `tickets`, `duration_ms` |
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
| `test_too_many_rows` | CSV из 10 001 заявки | `InvalidInput(reason="too_many_rows")`; репозиторий не вызван |
| `test_pool_timeout_is_dependency_unavailable` | фабрика соединений поднимает `PoolTimeout` | `DependencyUnavailable(reason="db_unavailable")`; репозиторий не вызван; записи `db_query_failed` (`query = replace_region_data`) и `data_load_failed` уровня `error` |
| `test_unknown_region_code_bounded_in_log` | код региона из 5000 символов с переводом строки | в записи `data_load_failed` поле `region` — 50 символов |
| `test_logs_no_addresses` | загрузка с промахами кэша и невалидными строками | ни в одной записи лога нет адресов и текста строк файла — только счётчики и коды причин |

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

## `src/api/schemas/generated/common.py` — LocalDateTime

> Мок не нужен: проверка сгенерированной по `specs/common.yaml` модели (`make gen-api`) —
> она же будет разбирать время во входных параметрах операций.

| Test | Scenario | Expected result |
|---|---|---|
| `test_local_datetime_accepts_local_time` | `"2026-09-23T13:20:00"` | принято, значение не изменено |
| `test_local_datetime_rejects_zone` | `"2026-09-23T13:20:00Z"`, `"2026-09-23T13:20:00+03:00"` | `pydantic.ValidationError` — время с поясом не принимается |
| `test_local_datetime_rejects_other_forms` | `"2026-09-23T13:20:00.5"`, `"2026-09-23 13:20:00"`, `"2026-09-23T13:20"`, `""` | `pydantic.ValidationError` |
| `test_local_datetime_rejects_out_of_range` | `"2026-13-01T10:00:00"`, `"2026-09-32T10:00:00"`, `"2026-09-23T24:00:00"`, `"2026-09-23T10:60:00"` | `pydantic.ValidationError` — месяц, день, час и минута вне допустимых диапазонов |

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
| `smoke_backend_migrates_on_start` | `make up` на volume БД, оставшемся от прежнего запуска стенда; `docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt'` | `migrate` — `Exited (0)`, в `docker compose logs migrate` JSON-запись о применении ревизии `5d23f2956ce7`; `backend` стартует после него и становится `healthy`; в БД шесть таблиц и `alembic_version` |
| `smoke_restart_does_not_migrate_again` | повторный `make up` | `migrate` снова `Exited (0)`, в его логе нет записи о применении ревизии; `backend` `healthy` |
| `smoke_backend_connects_as_app_rw` | `docker compose exec db psql … -c "SELECT DISTINCT usename FROM pg_stat_activity WHERE datname = current_database() AND backend_type = 'client backend' AND pid <> pg_backend_pid()"` | соединения пула приложения — под `app_rw`, не под владельцем схемы |
| `smoke_backend_has_no_owner_credentials` | `docker compose exec backend env` | нет ни `MIGRATION_DATABASE_URL`, ни `APP_RW_PASSWORD`, ни `APP_RO_PASSWORD`; `POSTGRES_PASSWORD` тоже нет — в `DATABASE_URL` только пароль `app_rw` |
| `smoke_db_port_on_loopback` | `docker compose port db 5432`; с хоста `psql -h 127.0.0.1 -p "$DB_PORT" -U app_ro -d "$POSTGRES_DB" -c 'SELECT count(*) FROM regions'` | порт опубликован только на `127.0.0.1:${DB_PORT}`; `app_ro` читает, запись под ним отклоняется правами |
| `smoke_backend_local_time` | `docker compose exec backend python -c "import time; print(time.strftime('%z'))"` | `+0300`; метки `timestamp` в логе `backend` совпадают с местным временем, а не с UTC |
| `smoke_migration_failure_blocks_backend` | в `.env` временно другой `POSTGRES_PASSWORD` (в томе БД остаётся прежний); `docker compose up -d` | `migrate` — `Exited (1)`, последняя строка его лога — JSON `migration_failed`; `docker compose up` завершается ошибкой «service "migrate" didn't complete successfully»; остановленный `backend` не стартует, уже запущенный с неизменёнными настройками продолжает работать; после возврата значения `make up` поднимает стенд |
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
