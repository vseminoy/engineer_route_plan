# Sequence-диаграммы — `alembic/`

## Старт стенда: миграции, затем приложение

Схема БД доводится до последней ревизии при каждом `docker compose up` отдельным разовым
сервисом `migrate` — тем же образом, что `backend`, с командой `alembic upgrade head`.
`backend` стартует только после его успешного завершения. Адрес владельца схемы
(пользователь `POSTGRES_USER` образа PostGIS) и пароли ролей есть только в окружении
`migrate`; `backend` получает один адрес — роли `app_rw`, у которой права только на
данные: приложение не может ни изменить схему, ни узнать учётные данные владельца.
`app_ro` — роль только на чтение, для ручных запросов к стенду.

Ревизия применяется в одной транзакции: ошибка на любом DDL откатывает её целиком, и
схема остаётся на предыдущей ревизии. Записи Alembic идут через stdlib `logging` и
выходят в том же JSON-формате, что и записи приложения; параметры SQL-операторов (в них
пароли ролей) в текст ошибок не попадают.

```mermaid
sequenceDiagram
    participant Compose as docker compose
    participant DB as db (PostgreSQL + PostGIS)
    participant Mig as migrate: alembic upgrade head
    participant App as backend: uvicorn (api)

    Compose->>DB: старт
    DB-->>Compose: healthy (pg_isready)
    Compose->>Mig: старт migrate
    Mig->>DB: подключение владельцем схемы
    alt БД недоступна или отказала в подключении
        Mig->>Mig: лог migration_failed (error, стек)
        Mig-->>Compose: выход с кодом ≠ 0
        Compose-->>App: не стартует (зависимость не выполнена)
    else схема уже на последней ревизии
        Mig->>Mig: лог: ревизий к применению нет
        Mig-->>Compose: выход с кодом 0
    else есть неприменённые ревизии
        Mig->>DB: BEGIN, DDL ревизии (таблицы, ограничения, индексы, COMMENT ON, роли app_rw / app_ro, GRANT)
        alt DDL ревизии не выполнился
            DB-->>Mig: ошибка SQL
            Mig->>DB: ROLLBACK (схема остаётся на предыдущей ревизии)
            Mig->>Mig: лог migration_failed (error, стек)
            Mig-->>Compose: выход с кодом ≠ 0
            Compose-->>App: не стартует (зависимость не выполнена)
        else
            Mig->>DB: UPDATE alembic_version, COMMIT
            Mig->>Mig: лог (revision)
            Mig-->>Compose: выход с кодом 0
        end
    end
    Compose->>App: старт backend (только после кода 0 у migrate)
    App->>DB: пул подключений ролью app_rw (открывается без ожидания)
    App-->>Compose: /health → 200, контейнер healthy
```

Сервис, вышедший на миграции, виден как `Exited (1)` у `migrate` в `docker compose ps -a`,
`backend` при этом в состоянии `Created`; причина — в последних строках
`docker compose logs migrate`. `/health` о состоянии схемы не сообщает: приложение с
неприменённой ревизией не запускается вовсе.

Ошибка запроса к БД во время работы приложения — ветка «БД или OSRM недоступны» общей схемы
в [`src/api/routes/sequence_diagrams.md`](../src/api/routes/sequence_diagrams.md#ошибки-любой-операции--единый-обработчик):
обёртка репозитория пишет `db_query_failed` (имя запроса aiosql, `sqlstate`) и поднимает
`DependencyUnavailable` → `503` без тела. Ошибка, которую повтор не исправит (нарушено
ограничение, неверные данные), — та же запись `db_query_failed` и `DatabaseFailure` → `500`
без тела и без повторной записи в обработчике.
