# Полная спецификация — Backend

Родительский документ: [`03_tor_backend.md`](03_tor_backend.md). Словарь исходных полей — [`07_data_dictionary.md`](07_data_dictionary.md).

## 1. Модель данных (логическая)

```
Region 1──* EngineerSet   (default — демо-набор, всегда один; generated — любое число)
Region 1──* Ticket
EngineerSet 1──* Engineer
EngineerSet 1──* Plan      (план и baseline строятся и сравниваются в пределах набора)
Engineer *──* Skill        (1..3 навыка на инженера, BR-06)
Engineer 1──1 VehicleType
Engineer 1──* EquipmentStock (опционально, доп. возможность FR-20, в MVP отсутствует)
Ticket   *──1 Skill        (ровно один требуемый навык)
Ticket   *──0..1 VehicleType (требуемый транспорт, если задан)
Ticket   1──1 Priority     (ранг типа работ: 1 — авария, 2 — подключение, 3 — ремонт/дозаказ; BR-12)
Plan     1──* Assignment
Assignment *──1 Ticket
Assignment *──1 Engineer
Plan     1──* ReplanEvent (история событий, приведших к текущей версии плана)
```

## 2. Справочники (см. также `07_data_dictionary.md`)

| Справочник | Значения |
|---|---|
| `Skill` (навык) | `local_work` (локальные работы), `connection` (подключения и дозаказы), `emergency` (аварийные работы) |
| `VehicleType` (транспорт) | `car`, `foot`, `bike`, `public_transport` |
| `Priority` (приоритет заявки) | ранг — целое ≥ 1, меньше — срочнее: `1` — авария, `2` — подключение, `3` — ремонт (локальная заявка) и дозаказ (BR-12). Ранг задаётся той же конфигурируемой таблицей соответствия типов заявок, что и навык; новый тип работ с новым приоритетом — новая строка таблицы, без изменения схемы БД |
| `TicketStatus` | `not_sent`, `sent`, `en_route`, `in_progress`, `completed`, `cancelled`, `overdue` |
| `UnassignedReason` | `no_skill`, `no_time_slot`, `no_vehicle`, `shift_overflow`, `no_equipment`, `all_eligible_engineers_booked_elsewhere` |

`no_equipment` достижим только если реализована дополнительная возможность FR-20 (BR-11); в обязательном MVP оборудование не моделируется как ограничение, поэтому этот код в MVP-конфигурации никогда не возвращается процедурой атрибуции (`08_algorithm.md` §4.2).

`all_eligible_engineers_booked_elsewhere` — заявка технически подходит хотя бы одной бригаде (навык/транспорт/окно/оборудование в порядке), но все такие бригады в это время уже заняты другими заявками; выявляется только процедурой атрибуции причины ([`08_algorithm.md` §4.2](08_algorithm.md#42-атрибуция-причины-отказа)), а не первым проваленным чек-флагом — иначе эта ситуация ошибочно попадала бы в `no_time_slot`, хотя причина другая (дефицит именно квалифицированных бригад в моменте, а не невозможность окна как такового).

Соответствие «Тип заявки ВК/HD → Skill» — конфигурируемая таблица маппинга (не хардкод), см. `07_data_dictionary.md` раздел «Маппинг типов заявок».

## 3. Схема БД (DDL, диалект PostgreSQL; применяется через Alembic raw-SQL миграции, без ORM-моделей)

Ниже — актуальная схема (после миграций `5d23f2956ce7`, `cb3db41d521a`, `c124884e0c63`,
`1b0ce84eb128`, `46c1bba9efff`); точные типы, ограничения и комментарии колонок — в
`back/alembic/versions/`, это единственный источник истины при расхождении. Координаты —
PostGIS `geometry(Point, 4326)`, а не отдельные `lat`/`lon`. Учёт оборудования
(`equipment_stock`, `ticket.required_equipment`) — доп. возможность FR-20/BR-11, в
обязательный MVP не входит и в схеме отсутствует.

```sql
CREATE TABLE regions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,      -- 'east' | 'south_east' | 'south_center'
    name            TEXT NOT NULL,
    office_address  TEXT NOT NULL,
    office_geom     geometry(Point, 4326) NOT NULL
);

CREATE TABLE engineer_sets (                  -- набор бригад региона: demo (default) | generated
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_id      BIGINT NOT NULL REFERENCES regions(id),
    name           TEXT NOT NULL,             -- уникально в регионе; у demo всегда 'default'
    kind           TEXT NOT NULL,             -- 'demo' | 'generated'
    engineers      INTEGER NOT NULL,          -- параметр генератора, 1..30
    morning_share  DOUBLE PRECISION NOT NULL, -- параметр генератора, 0..1
    evening_share  DOUBLE PRECISION NOT NULL, -- параметр генератора, 0..1
    seed           TEXT NOT NULL              -- зерно генератора
);

CREATE TABLE engineers (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    engineer_set_id BIGINT NOT NULL REFERENCES engineer_sets(id), -- регион бригады — регион её набора
    name          TEXT NOT NULL,
    start_geom    geometry(Point, 4326) NOT NULL,
    shift_start   TIME NOT NULL,
    shift_end     TIME NOT NULL,
    vehicle_type  TEXT NOT NULL,
    skills        TEXT[] NOT NULL            -- 1..3 значений Skill
);

CREATE TABLE tickets (
    id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_id                 BIGINT NOT NULL REFERENCES regions(id),
    external_id               TEXT NOT NULL,  -- поле "Заявка" из исходных данных
    type_bk                   TEXT,           -- исходное поле "Тип заявки BK"; NULL — поле пусто
    type_hd                   TEXT NOT NULL,  -- исходное поле "Тип заявки HD"
    required_skill            TEXT NOT NULL,  -- выведено маппингом BK/HD -> Skill
    required_vehicle          TEXT,           -- NULL, если не задано
    priority                  SMALLINT NOT NULL, -- ранг BR-12, >= 1
    district                  TEXT,
    address                   TEXT NOT NULL,
    geom                      geometry(Point, 4326) NOT NULL,
    window_start              TIMESTAMP NOT NULL, -- naive datetime, пояс региона
    window_end                TIMESTAMP NOT NULL,
    duration_min              INTEGER NOT NULL,   -- из Нормативы.xlsx по типу работы
    status                    TEXT NOT NULL,
    received_at               TIMESTAMP NOT NULL, -- момент фактического появления заявки (BR-14, BR-33)
    cancelled_after_dispatch  BOOLEAN NOT NULL DEFAULT FALSE -- BR-23
);

CREATE TABLE plans (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_id       BIGINT NOT NULL REFERENCES regions(id),
    engineer_set_id BIGINT NOT NULL REFERENCES engineer_sets(id), -- набор, для которого построен план
    plan_date       DATE NOT NULL,
    algorithm       TEXT NOT NULL,           -- 'or_tools' | 'baseline_fcfs'
    parent_plan_id  BIGINT REFERENCES plans(id), -- ссылка на план до перепланирования
    status          TEXT NOT NULL,           -- 'running' | 'done' | 'failed'
    failed_reason   TEXT,                    -- заполнено только при status = 'failed'
    created_at      TIMESTAMP NOT NULL
);

CREATE TABLE assignments (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id            BIGINT NOT NULL REFERENCES plans(id),
    ticket_id          BIGINT NOT NULL REFERENCES tickets(id),
    engineer_id        BIGINT REFERENCES engineers(id), -- NULL — заявка не назначена
    sequence_no        INTEGER,               -- порядок посещения у бригады; NULL у неназначенной
    planned_arrival    TIMESTAMP,             -- с точностью до минуты; NULL у неназначенной
    travel_time_min    INTEGER,               -- минуты, округление вверх; NULL у неназначенной
    travel_distance_m  INTEGER,               -- метры по дорожной сети; NULL у неназначенной
    unassigned_reason  TEXT,                  -- UnassignedReason enum; NULL у назначенной
    explanation        TEXT NOT NULL          -- готовый человекочитаемый текст
);

CREATE TABLE replan_events (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id         BIGINT NOT NULL REFERENCES plans(id),  -- план, к которому применено событие
    event_type      TEXT NOT NULL,           -- 'new_urgent_ticket' | 'new_ticket' | 'ticket_cancelled' | 'engineer_unavailable'
    payload         JSONB NOT NULL,          -- детали события
    triggered_at    TIMESTAMP NOT NULL,
    result_plan_id  BIGINT REFERENCES plans(id) -- итоговый план после обработки события
);
```

Индексы: `tickets(region_id, window_start)`, `tickets(region_id, status)`, GiST на всех
геометриях, `assignments(ticket_id)`, `assignments(engineer_id)`,
`engineers(engineer_set_id)`, `plans(engineer_set_id)` и внешние ключи — полный список и
`COMMENT ON` каждой колонки в `back/alembic/versions/`.

## 3.1. Слой доступа к данным (aiosql)

Доступ к БД — без ORM. SQL-запросы живут в `.sql`-файлах, сгруппированных по агрегату, и подключаются как объект `queries` с методами, имя которых берётся из аннотации `-- name:`.

```
back/
  alembic/
    versions/               # Alembic-миграции (raw SQL, DDL из раздела 3)
  queries/
    regions.sql
    engineers.sql
    engineer_sets.sql
    tickets.sql
    plans.sql
    assignments.sql
    replan_events.sql
```

Пример `queries/tickets.sql`:

```sql
-- name: get_ticket^
-- Одна заявка по id, или None
SELECT * FROM tickets WHERE id = :ticket_id;

-- name: list_open_tickets_by_region
-- Заявки региона, ещё не закрытые (участвуют в (пере)планировании)
SELECT * FROM tickets
WHERE region_id = :region_id
  AND status NOT IN ('completed', 'cancelled');

-- name: set_ticket_status!
UPDATE tickets SET status = :status WHERE id = :ticket_id;

-- name: insert_ticket<!
INSERT INTO tickets (external_id, region_id, type_bk, type_hd, required_skill,
                      required_vehicle, priority, district, address, geom,
                      window_start, window_end, duration_min, status, received_at)
VALUES (:external_id, :region_id, :type_bk, :type_hd, :required_skill,
        :required_vehicle, :priority, :district, :address, :geom,
        :window_start, :window_end, :duration_min, :status, :received_at)
RETURNING id;
```

Суффиксы аннотаций aiosql: `^` — одна строка или `None`, без суффикса — список строк, `!` — операция изменения без результата, `<!` — insert с возвратом id. Подключение в коде:

```python
import aiosql
import psycopg

queries = aiosql.from_path("queries", "psycopg")
conn = psycopg.connect("postgresql://user:password@localhost:5432/plan")

ticket = queries.get_ticket(conn, ticket_id=101)          # вызов как метод
open_tickets = queries.list_open_tickets_by_region(conn, region_id=1)
queries.set_ticket_status(conn, ticket_id=101, status="completed")
```

Репозитории сервисного слоя (раздел 5–6) оборачивают вызовы `queries.*` и приводят строки к доменным dataclass-объектам (`Ticket`, `Engineer`, `Assignment`) — типизация обеспечивается на этой границе, а не генерируется автоматически (в отличие от `sqlc`), что и было осознанным выбором при отказе от кодогенерации в пользу зрелости библиотеки.

## 4. API-контракт

Базовый префикс: `/api/v1`. Формат: JSON. Аутентификация не требуется (NFR-04).

### 4.1. Данные

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/data/upload` | Загрузка файла заявок региона; тело `multipart/form-data`: `region`, `tickets_file` (`.csv` или `.json`, до 1 МБ). Бригады региона — демо-бригады от генератора backend: создаются при первой загрузке региона и сохраняются при следующих с теми же id, у них обновляются только точки старта (офис и удалённые города — по файлу). Заявки региона заменяются, планы удаляются, всё в одной транзакции; ответ — число загруженных бригад и заявок, пропущенные и невалидные строки с причиной |
| `POST` | `/data/demo` | Загрузить встроенный демо-набор региона; тело — JSON `{"region": "east"}`; заявки заменяются, бригады сохраняются, планы удаляются так же, как при загрузке файла. `POST`, потому что операция удаляет данные: `GET` клиенты и прокси вправе повторять сами |
| `GET` | `/regions` | Список регионов из конфигурации backend: код и название |
| `GET` | `/tickets?region=east` | Все заявки региона: адрес, точка, окно, навык, транспорт, приоритет, длительность, статус. Назначения заявок бригадам — в плане (`GET /plan/{plan_id}`) |
| `GET` | `/engineers?region=east&engineer_set_id=...` | Бригады региона или одного набора бригад: навыки, транспорт, смена, точка старта. Без `engineer_set_id` — бригады набора `default` |

Код региона — из `GET /regions`; код, которого нет в конфигурации, — `400` у параметра `region`.
Регион без загруженных данных — пустой список заявок и бригад. Точный контракт операций —
`specs/openapi.yaml`.

### 4.1.1. Наборы бригад региона

Регион может держать несколько наборов бригад одновременно — набор `default` (создаётся
первой загрузкой данных региона тем же генератором, что и раньше, и обновляется вместе с
ней; удалить нельзя) и любое число дополнительных наборов, которые пользователь создаёт
своими параметрами генератора (см. врезку «Наборы бригад региона» в
[`01_business_requirements.md`](01_business_requirements.md#5-функциональные-требования)).
План и baseline строятся по конкретному набору и сравниваются только внутри него.

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/engineer-sets?region=east` | Наборы бригад региона: id, название, вид (`demo`/`generated`), параметры генератора, число бригад |
| `POST` | `/engineer-sets` | Создать дополнительный набор: `region`, `name`, `engineers`, `morning_share`, `evening_share`, `seed`; `201` с созданным набором; `409`, если `name` занято в регионе |
| `DELETE` | `/engineer-sets/{engineer_set_id}` | Удалить дополнительный набор вместе с его планами; `204`; `409` при попытке удалить `default` |

`POST /plan/build` принимает необязательный `engineer_set_id` (без него — набор `default`);
ответ плана и `POST /plan/{plan_id}/replan` всегда возвращают `engineer_set_id` набора, по
которому план построен; `GET /plan/{plan_id}/compare` сравнивает только планы одного набора,
иначе — `400`.

### 4.2. Планирование

Построение плана — асинхронное: `POST /plan/build` ставит расчёт в очередь и сразу отвечает,
не дожидаясь OSRM и солвера; клиент узнаёт результат, опрашивая `GET /plan/{plan_id}`, пока
план не перейдёт из `running` в `done` или `failed`.

`POST /plan/build`

Запрос:
```json
{
  "region": "east",
  "plan_date": "2026-08-17",
  "algorithm": "or_tools",      // "or_tools" | "baseline_fcfs"
  "engineer_set_id": null       // необязательное; без него — набор default
}
```

Ответ (`202`) — план поставлен в очередь, маршрутов ещё нет:
```json
{
  "plan_id": 42,
  "algorithm": "or_tools",
  "status": "running",
  "engineer_set_id": 7
}
```

`GET /plan/{plan_id}` — тот же формат, в любом из трёх состояний `status`:

- **`running`** — расчёт ещё идёт, тело как у ответа `POST /plan/build`;
- **`done`** — расчёт закончен успешно:
```json
{
  "plan_id": 42,
  "algorithm": "or_tools",
  "status": "done",
  "engineer_set_id": 7,
  "engineers": [
    {
      "engineer_id": 3,
      "name": "Бригада Соколов",
      "route": [
        {
          "ticket_id": 101,
          "sequence_no": 1,
          "planned_arrival": "2026-08-17 10:05",
          "travel_time_min": 18,
          "travel_distance_km": 6.2,
          "explanation": "Назначена бригада «Соколов»: обладает навыком «Подключение», свободна в окне 10:00–12:00, доезжает на автомобиле за 18 мин."
        }
      ],
      "total_distance_km": 21.4,
      "total_travel_time_min": 54,
      "idle_time_min": 126
    }
  ],
  "unassigned": [
    {
      "ticket_id": 118,
      "reason_code": "no_time_slot",
      "explanation": "Ни одна бригада с навыком «Авария» не успевает прибыть в окно 08:00–10:00 без нарушения ранее назначенных заявок."
    }
  ],
  "metrics": {
    "engineers_used": 9,
    "total_distance_km": 187.3,
    "distance_by_engineer": {"3": 21.4, "5": 14.0},
    "assigned_count": 94,
    "unassigned_count": 6,
    "idle_time_by_engineer_min": {"3": 126, "5": 240}
  }
}
```
- **`failed`** — расчёт не закончился: `osrm_unavailable`/`db_unavailable` — OSRM или БД
  недоступны, `build_error` — непредусмотренная ошибка, `timeout` — солвер не уложился в
  бюджет времени и был прерван вотчдогом, `shutdown` — план остался `running` при остановке
  сервера и закрыт стартовой чисткой:
  `{"plan_id": 42, "algorithm": "or_tools", "status": "failed", "engineer_set_id": 7, "failed_reason": "osrm_unavailable"}`.

`idle_time_min` / `idle_time_by_engineer_min` (FR-23, M) — простой бригады = длина смены минус (суммарное время визитов + суммарное время в пути); поле **обязательно** к возврату API, но участвует только в отображении — не влияет на целевую функцию солвера (раздел 5) и не входит в сравнение с baseline в `/plan/{plan_id}/compare`.

Строка плана появляется в БД в момент постановки в очередь (`status = running`), без
`assignments` — они вставляются одним пакетом, когда расчёт заканчивается успехом. Если
процесс backend перезапускается во время расчёта, план так и остаётся в `running`: за это
отвечает вызывающий (повторный `POST /plan/build`), отдельного механизма восстановления нет.

`GET /plan/{plan_id}/compare?baseline_plan_id=...` — сравнение обязательных метрик плана
из пути (`plan_id`) с baseline-планом (`baseline_plan_id`), по одной записи на метрику,
`delta` = план минус baseline (отрицательное значение — план лучше baseline). Оба плана
должны быть `status=done`, иначе — `400`; план из пути проверяется первым, и если он ещё
не готов, baseline вообще не читается. Оба плана должны быть одного `engineer_set_id` —
сравнение планов разных наборов недопустимо и тоже даёт `400`.
```json
[
  {"metric": "engineers_used", "main": 9, "baseline": 13, "delta": -4},
  {"metric": "total_distance_km", "main": 187.3, "baseline": 244.9, "delta": -57.6}
]
```

### 4.3. Перепланирование

`POST /plan/{plan_id}/replan`

Запрос (один из типов события; `new_ticket` — дополнительная возможность FR-34):
```json
{
  "event_type": "new_urgent_ticket",
  "triggered_at": "2026-08-17 13:20",
  "ticket": { "...полный набор полей заявки, required_skill=emergency, duration_min=80" }
}
```
`duration_min=80` — время на объекте (только тех. работы, без документов, раздел 8); 100-минутный норматив BR-14 = дорога до ТКД + 80 мин на объекте, а не значение поля `duration_min`. Дорога в плане — расчётное время в пути, а не резерв 20 мин (раздел 8). Необязательное поле `reaction_min` (60–120, по умолчанию 120) — целевое время реакции от `triggered_at` до прибытия (BR-33).
```json
{
  "event_type": "new_ticket",
  "triggered_at": "2026-08-17 13:20",
  "ticket": { "...полный набор полей заявки, required_skill ∈ {local_work, connection}" }
}
```
`new_ticket` — новая обычная заявка в течение дня (BR-31): только вставка в свободный интервал, без вытеснения и перестройки других маршрутов.
```json
{ "event_type": "ticket_cancelled", "triggered_at": "2026-08-17 13:20", "ticket_id": 118 }
```
```json
{ "event_type": "engineer_unavailable", "triggered_at": "2026-08-17 13:20", "engineer_id": 5 }
```

Ответ (`200`) — план в формате `POST /plan/build`, дополненный блоком diff:
```json
{
  "plan_id": 43,
  "parent_plan_id": 42,
  "engineer_set_id": 7,
  "...": "...",
  "diff": {
    "changed_assignments": [
      { "ticket_id": 87, "before_engineer_id": 3, "after_engineer_id": 3, "before_sequence_no": 2, "after_sequence_no": 3 }
    ],
    "newly_assigned": [118],
    "newly_unassigned": [],
    "reassigned_from_unavailable_engineer": [],
    "plan_stability": 1
  }
}
```

### 4.4. Заявки: статусы

`PATCH /tickets/{ticket_id}/status`
```json
{ "status": "completed" }
```
Правило: переход в `completed`/`cancelled` фиксируется диспетчером (BR-25) и исключает заявку из последующих `/replan`.

### 4.5. Ошибки

Один принцип для всех эндпоинтов. Схема ошибки и ответы ошибок описаны в спеке один раз — в `specs/common.yaml`; операции ссылаются на них.

**`400` — единственный код ошибки с телом.** Ошибка входных данных; тело — ровно одно из двух полей:
```json
{ "message": "Колонка 'Начало' не найдена в файле" }
```
```json
{ "fields": [
  { "name": "region", "message": "Неизвестный регион" },
  { "name": "tickets_file", "message": "Файл должен быть .csv или .json" }
] }
```
- `message` — ошибка запроса в целом (не привязана к одному параметру);
- `fields` — ошибки конкретных входных параметров, фронтенд показывает каждую у своего поля формы. `name` — имя параметра как в контракте (поле тела, query-, path- или form-параметр; вложенность — через точку, индекс — в `[]`: `engineers[2].skills`);
- тексты — на русском, для диспетчера, без SQL, трассировок и ответов внешних сервисов;
- ошибки валидации запроса возвращаются как `400` с `fields`; `422` не используется.

**Остальные коды ошибок — без тела.** Текст для диспетчера формирует фронтенд по паре «эндпоинт + код ответа», поэтому один код внутри эндпоинта означает ровно одну ситуацию:

| Код | Ситуация |
|---|---|
| `404` | запрошенный ресурс не найден (план, заявка) |
| `413` | загружаемый файл слишком большой |
| `500` | непредусмотренная ошибка сервера |
| `501` | эндпоинт ещё не реализован (демо-стенд в процессе разработки) |
| `503` | недоступна зависимость — БД, OSRM или внешний геокодер; запрос можно повторить |

| Ситуация | Код | Тело |
|---|---|---|
| невалидные параметры запроса | `400` | `fields` |
| неверный формат файла CSV/JSON | `400` | `message` (или `fields`, если ошибка в конкретной колонке/строке) |
| план не найден | `404` | — |
| OSRM недоступен | `503` | — |

**`X-Request-ID`.** У каждого ответа, включая ошибки, есть заголовок `X-Request-ID` — идентификатор запроса, по которому в логах backend находятся все записи этого запроса. Фронтенд может показать его диспетчеру для обращения в поддержку.

## 5. Алгоритм построения плана (OR-Tools RoutingModel)

1. **Узлы:** депо на бригаду = стартовая точка (`engineer.start_lat/lon`); узлы-заявки = координаты `ticket`. Матрица времени — из OSRM (`table`), отдельно по профилям `car`/`foot`/`bike`, для `public_transport` — усреднённый коэффициент от профиля `car` (BR-09, условие §40).
2. **Vehicles:** одна «машина» OR-Tools на бригаду (BR-01), капасити по времени = длина смены.
3. **Time windows:** `AddDimension` по времени с жёстким окном `[window_start, window_end]` на узел-заявку (BR-20); длительность визита — `duration_min` из норматива (`07_data_dictionary.md`).
4. **Квалификация/транспорт:** через `SetAllowedVehiclesForIndex` — узел-заявка разрешён только тем «машинам»-бригадам, у которых есть требуемый навык и (если задан) требуемый тип транспорта (BR-06–BR-08). Жёсткое ограничение, не штраф.
5. **Неназначаемые заявки:** `AddDisjunction([node], penalty)` — позволяет солверу оставить заявку без назначения с высоким штрафом вместо падения в инфизибл; штраф ранжирован по приоритету: авария ≫ подключение ≫ ремонт/дозаказ (BR-12), чтобы при нехватке ресурсов в первую очередь оставались непокрытыми заявки низкого приоритета.
6. **Целевая функция:** первично — минимизация суммы штрафов за неназначенные заявки (⇒ максимум выполненных); вторично — минимизация количества использованных «машин» (через фиксированную стоимость `SetFixedCostOfVehicle` на бригаду); третично — минимизация суммарного времени в пути. Порядок соответствует BR-приоритету раздела 3 `01_business_requirements.md`.
7. **Explainability:** после решения — постобработка каждого назначения в текст по шаблону (бригада, навык, окно, время в пути, оборудование); для неназначенных — определение конкретной нарушенной причины через повторную проверку ограничений по кандидатам (какое именно ограничение отсеяло всех бригад).

## 6. Алгоритм перепланирования (min-change)

> Механизм ниже — сокращённая версия для реализации API-контракта раздела 4.3. Полное обоснование и формальный протокол (Contract Net: объявление задания → локальные ставки бригад → выбор победителя → каскад вытеснения глубиной 1) — [`08_algorithm.md`](08_algorithm.md#5-событие-перепланирования-fr-13). Шаги 2–3 ниже соответствуют разделам 5.1–5.2 того документа.

1. Загрузить текущий план (`plan.parent_plan_id` = предыдущий).
2. Применить событие:
   - Состояние бригад на момент `triggered_at` (для всех типов событий): заявки `completed`/`cancelled` исключены (BR-25); заявка `in_progress` зафиксирована — бригада освобождается в точке этой заявки не раньше её планового окончания (прибытие + `duration_min`), начатая работа не прерывается (BR-32); заявки `en_route` и ещё не начатые можно перестраивать. Свободная бригада без начатой работы стартует из точки последней выполненной заявки (или из депо) в `triggered_at`.
   - `new_urgent_ticket` (авария): кандидаты — бригады с навыком `emergency`; «ставка» бригады — время прибытия на аварию из её состояния на `triggered_at` и доп. время для её маршрута. Предпочтение — бригадам, успевающим в целевое время реакции `triggered_at + reaction_min` (BR-33); среди них — минимальная ставка. Сначала — вставка без нарушения чужих окон (BR-13); если невозможно — вытеснение более низкоприоритетной не начатой заявки бригады-победителя: вытесненная заявка повторно торгуется среди остальных бригад без нарушения своего окна (каскад глубиной 1), иначе уходит в `unassigned` с причиной. Оставшаяся часть дня бригады-победителя пересчитывается. Если в целевое время не успевает никто — авария назначается бригаде с самым ранним прибытием, превышение фиксируется в объяснении; если нет ни одной бригады с навыком — `unassigned`.
   - `new_ticket` (обычная заявка, FR-34): вставка в свободный интервал маршрута допустимой бригады без сдвига окон и без вытеснения (BR-31); побеждает минимальная доп. время в пути; остальные назначения не меняются; если интервала нет — `unassigned` с причиной.
   - `ticket_cancelled`: удалить узел из маршрута бригады, сдвинуть последующие визиты по времени, остальные бригады не трогать.
   - `engineer_unavailable`: снять все ещё не начатые (`status` не `completed`/`cancelled`/`in_progress`) заявки бригады, попытаться вставить их в маршруты остальных бригад региона по тем же правилам ограничений, иначе — `unassigned`.
3. Ограничить область изменений: локальный поиск (insertion / 2-opt в окрестности изменённого участка) вместо полного перезапуска глобального солвера — обеспечивает `PlanStability` (BR-17).
4. Сформировать `diff` относительно `parent_plan_id`.

## 7. Baseline-алгоритм (обязателен для сравнения)

Алгоритм задан дословно в ТЗ (раздел 2.3): «*Для единого сравнения базовый вариант задаётся так: заявки обрабатываются по порядку поступления и назначаются первому по порядку во входных данных доступному инженеру, который удовлетворяет обязательным ограничениям; порядок посещения соответствует порядку назначения. Глобальная оптимизация в базовом варианте не выполняется.*» «FCFS» (First-Come-First-Served) — стандартное отраслевое имя для этого поведения, используется как краткое обозначение в API (`algorithm: "baseline_fcfs"`).

Псевдокод:
```
for ticket in tickets_in_input_order:
    for engineer in engineers_in_input_order:
        if engineer has required_skill and (no required_vehicle or matches)
           and inserting ticket at end of engineer's route keeps all time windows valid
           and does not exceed shift_end:
            assign ticket to engineer at end of route
            break
    else:
        mark ticket unassigned with reason
```
Никакой перестановки порядка, никакой глобальной оптимизации — эталон для метрик FR-12.

## 8. Модуль расчёта нормативов длительности

Источник — `docs/Нормативы.xlsx` (мин.):

| Тип работы | Дорога до клиента | Технические работы | Документы | Базовый норматив |
|---|---|---|---|---|
| Подключение клиентов (базовая) | 20 | 60 | 10 | 90 |
| Авария на ТКД | 20 | 80 | 0 | 100 |
| Дозаказ оборудования | 20 | 10 | 10 | 40 |
| Локальная заявка/ремонт у клиента | 20 | 30 | 0 | 50 |

Компонент «Дорога до клиента/ТКД» — переменная величина для всех типов заявок (условие conditions.md **№45**): 20 мин — резерв, которым заявка бронирует время в графике при постановке (параметр `travel_reserve_min`, по умолчанию 20; увеличение допустимо, но редко). При распределении резерв заменяется реально рассчитанным временем в пути: `duration_min` = «Технические работы» + «Документы» (время на объекте), а время в пути между точками считается матрицей OSRM по профилю транспорта бригады (BR-10) и добавляется к нему при построении расписания. Резерв используется только там, где маршрута ещё нет, — при бронировании слота ([`08_algorithm.md` §5.4](08_algorithm.md#54-обобщение-на-процесс-накопления-заявок-условие-43)).

Для **Аварии** («дорога входит в норматив выполнения нормативной аварийной заявки. На дорогу до ТКД выделяется 20 минут (т.е. 80 минут на точке)»):
- `duration_min` = 80 (только «Технические работы», без «Документов»);
- 100-минутный норматив BR-14 (отсчёт с момента фактического поступления заявки) = дорога + 80: при бронировании — резерв 20 + 80, в плане — расчётное время в пути + 80;
- срок по аварии контролируется целевым временем реакции 1–2 часа от поступления до прибытия (BR-33, параметр `reaction_min`), а не фиксированной 20-минутной дорогой.

## 9. Тестовые сценарии (юнит/интеграционные, обязательны к покрытию)

1. Бригада без нужного навыка не получает заявку требующего этот навык (жёсткое ограничение).
2. Заявка с требуемым транспортом не назначается бригаде с другим транспортом.
3. Прибытие бригады к заявке всегда внутри `[window_start, window_end]`.
4. Суммарная занятость бригады не превышает её смену.
5. Аварийная заявка, добавленная в 13:20, может вытеснить в графике заявку более низкого приоритета, не нарушая её окно; время в пути до неё — расчётное (OSRM), а не резерв 20 мин.
5a. Бригада, у которой в момент аварии заявка в статусе `in_progress`, завершает её: эта заявка остаётся в плане на месте, а прибытие бригады на аварию — не раньше планового окончания начатой работы.
5b. Среди бригад с навыком `emergency` выбирается та, что успевает в целевое время реакции; если не успевает никто — бригада с самым ранним прибытием, и объяснение сообщает о превышении.
5c. Новая обычная заявка (`new_ticket`) вставляется только в свободный интервал: остальные назначения плана не меняются; при отсутствии интервала — `unassigned`.
5d. Внутри региона заявка из удалённого города (например, Домодедово) может быть назначена бригаде со стартом в Москве и наоборот — территория не является ограничением.
6. При отмене заявки план остальных бригад не пересобирается целиком (только затронутая бригада).
7. Baseline-план и основной план считаются независимо и дают сравнимые по формату метрики.
8. Заявка с `status = completed` не участвует в последующем `/replan`.
9. Загрузчик CSV корректно отфильтровывает пустые строки и служебную строку-сентинел `Заявка ∈ {"Адрес Офиса", "Адрес офиса"}` (см. `07_data_dictionary.md` §1) — эта строка используется только как источник координат старта бригад региона и не создаёт запись в таблице `ticket`.
10. Заявка с `Тип заявки HD = Авария` получает `required_skill = emergency` независимо от значения `Тип заявки BK` (проверка того, что маппинг не завязан на несуществующее в данных значение `BK = Авария`, см. `07_data_dictionary.md` §3).
