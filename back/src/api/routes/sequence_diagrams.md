# Sequence-диаграммы — `src/api/routes/`

## `GET /health`

Liveness-проверка процесса. Ошибочных веток нет: обработчик не выполняет
ввод-вывода (не обращается к БД и не ходит в OSRM) и ничем, кроме самого
факта ответа процесса, не может завершиться иначе как `200`.

```mermaid
sequenceDiagram
    participant Client
    participant API as api (health route)

    Client->>API: GET /health
    API-->>Client: 200 {status: "ok", version}
```

## `/api/v1/{path}` — заглушка нереализованных операций

Инфраструктура стенда, а не часть контракта: в `specs/openapi.yaml` не описана и в
генерируемую схему приложения не попадает. Принимает любой метод на любом пути под
`/api/v1`, зарегистрирована последней — роут реализованной операции объявлен раньше и
перехватывает запрос до неё. Совпадение ищется по паре «путь + метод», поэтому метод,
которого нет у реализованного пути, тоже попадает в заглушку и получает `501`, а не `405`.
Отвечает `501` без тела: текст «ещё не реализовано»
фронтенд строит по коду ответа. Когда реализована последняя операция, заглушка
удаляется, и неизвестный путь под `/api/v1` отвечает `404`.

В стенде Docker Compose запросы браузера идут через nginx фронтенда: он отдаёт
статику и проксирует `/api` в backend без изменения пути. Тело больше
`MAX_REQUEST_BODY_BYTES` nginx отклоняет сам, не передавая в backend.

```mermaid
sequenceDiagram
    participant Client as Client (браузер)
    participant Proxy as nginx (frontend)
    participant API as api (роутеры)
    participant Stub as api (заглушка /api/v1/{path})

    Client->>Proxy: METHOD /api/v1/...
    alt тело больше MAX_REQUEST_BODY_BYTES
        Proxy-->>Client: 413 без тела
    else
        Proxy->>API: METHOD /api/v1/... (путь без изменений)
        alt путь и метод совпали с реализованной операцией
            API-->>Proxy: ответ операции по контракту
        else ни одна реализованная операция не подошла
            API->>Stub: METHOD /api/v1/{path}
            Stub-->>Proxy: 501 без тела
        end
        Proxy-->>Client: ответ backend без изменений
    end
```

## Ошибки любой операции — единый обработчик

Общая схема для всех операций, включая `/health` и заглушку `/api/v1/{path}`; диаграммы
отдельных операций показывают только свои ветки и на эту ссылаются. Тело есть только у
`400` (`ValidationError` из `specs/common.yaml`: `message` либо `fields`), остальные коды
ошибок — без тела. `X-Request-ID` есть у каждого ответа: для ответов, прошедших
middleware запроса, его ставит она, для `500` — обработчик `Exception` из `contextvars`,
потому что работает снаружи пользовательских middleware.

Порядок снаружи внутрь: middleware запроса (`request_id`, запись
`http_request_finished`) → middleware предела тела (`MAX_REQUEST_BODY_BYTES`) → валидация
FastAPI → маршрут → `service` → (`queries`-репозиторий | `client` OSRM). Предел тела
проверяется дважды: по `Content-Length` — сразу, в middleware; без него — пока операция
читает тело, и тогда `413` собирает единый обработчик. Операция, которая тело не читает
(заглушка, `404`, `405`), отвечает своим кодом. Запрос, не сопоставленный ни одному роуту,
пишется в лог с `path="<unmatched>"`, а не с присланным путём. Ошибка БД или
OSRM логируется в месте возникновения и поднимается доменным исключением; бизнес-ошибку
логирует маршрут (`<операция>_failed`) и пробрасывает дальше; ответ собирает только
единый обработчик.

```mermaid
sequenceDiagram
    participant Client
    participant ReqMW as api (middleware запроса)
    participant SizeMW as api (middleware предела тела)
    participant API as api (валидация + маршрут)
    participant H as api (единый обработчик ошибок)
    participant Svc as service
    participant Dep as queries (БД) | client (OSRM)

    Client->>ReqMW: METHOD /path [X-Request-ID]
    ReqMW->>ReqMW: request_id = заголовок клиента, если допустим, иначе новый
    ReqMW->>SizeMW: запрос
    alt Content-Length больше MAX_REQUEST_BODY_BYTES
        SizeMW-->>ReqMW: 413 без тела, Connection: close (тело не читается)
    else
        SizeMW->>API: запрос
        alt операция читает тело, и оно превысило предел при чтении
            SizeMW->>H: исключение 413 из чтения тела (приём прерван)
            H-->>ReqMW: 413 без тела, Connection: close
        else тело не разбирается (не UTF-8, битая форма)
            API->>H: HTTPException 400
            H-->>ReqMW: 400 {message}
        else путь не найден или метод не разрешён (Starlette)
            API->>H: StarletteHTTPException
            H-->>ReqMW: 404 / 405 без тела
        else параметры не проходят ограничения контракта
            API->>H: RequestValidationError
            H->>H: лог request_validation_failed (путь-шаблон, имена первых 20 полей без значений, errors_total)
            H-->>ReqMW: 400 {fields: [{name, message}]} (не больше 20, тексты по type ошибки, на русском)
        else
            API->>Svc: вызов операции
            alt бизнес-проверка не пройдена
                Svc-->>API: InvalidInput(message | fields)
                API->>API: лог <операция>_failed (warning: reason, бизнес-параметры)
                API->>H: InvalidInput
                H-->>ReqMW: 400 {message} | {fields}
            else ресурс не найден
                Svc-->>API: NotFound
                API->>API: лог <операция>_failed (warning)
                API->>H: NotFound
                H-->>ReqMW: 404 без тела
            else противоречит состоянию ресурса
                Svc-->>API: Conflict
                API->>API: лог <операция>_failed (warning)
                API->>H: Conflict
                H-->>ReqMW: 409 без тела
            else БД или OSRM недоступны
                Svc->>Dep: запрос
                Dep->>Dep: лог db_query_failed | osrm_request_failed (технические детали)
                Dep-->>Svc: DependencyUnavailable from e
                Svc-->>API: DependencyUnavailable
                API->>API: лог <операция>_failed (error, тот же request_id)
                API->>H: DependencyUnavailable
                H-->>ReqMW: 503 без тела
            else операция ещё не реализована (заглушка)
                API-->>ReqMW: 501 без тела
            else успех
                Svc-->>API: результат
                API-->>ReqMW: 2xx по контракту
            end
        end
    end
    ReqMW->>ReqMW: лог http_request_finished (status, duration_ms)
    ReqMW-->>Client: ответ + X-Request-ID

    Note over ReqMW,H: Непредусмотренное исключение проходит сквозь middleware запроса<br/>(она пишет http_request_finished status=500 и пробрасывает его)
    H->>H: лог unhandled_error со стеком
    H-->>Client: 500 без тела + X-Request-ID из contextvars
```

## `GET /api/v1/regions`

Справочник регионов из конфигурации сервера (`data/regions.toml`), в порядке её записи.
Отвечает одинаково, загружены ли по региону данные или нет. Ввода-вывода нет: конфигурация
читается один раз, при старте приложения. Своих веток ошибок у операции нет, остаются
только общие (`500`).

```mermaid
sequenceDiagram
    participant Client
    participant API as api (маршрут regions)
    participant Svc as service (конфигурация регионов)

    Client->>API: GET /api/v1/regions
    API->>Svc: список регионов
    Svc-->>API: [(code, name)] в порядке конфигурации
    API-->>Client: 200 [{code, name}]
```

## `POST /api/v1/data/upload`, `POST /api/v1/data/demo`

Обе операции заменяют данные одного региона через загрузчик. Как загрузчик читает файл,
проверяет строки, ищет координаты и пишет в БД, и какими исключениями завершается, — на
диаграмме «Загрузка данных региона» диаграмм сервисного слоя (`src/service/`). Здесь показано,
что делает HTTP-слой и какой ответ получается из каждого исключения.

Обе операции — `POST`: загрузка удаляет планы региона, а `GET` клиенты и прокси вправе
повторять сами (кэш, prefetch, повторный запрос при возврате на вкладку).

На стенде nginx ждёт ответа `/api/v1/data/upload` и `/api/v1/data/demo` до 10 минут, а не 60 с, как у остальных:
с включённым Nominatim загрузка геокодирует промахи кэша по запросу в секунду и длится минуты.

Бригады файлом не принимаются: у региона демо-бригады от генератора. Они сохраняются между
загрузками с теми же id, загрузка обновляет у них только точки старта; планы региона
удаляются.

Любую ошибку самого загрузчика он логирует сам, один раз, событием `data_load_failed`
(`reason`, `region`, `source`, `duration_ms`). Маршрут её больше не логирует. Маршрут пишет
только `data_upload_failed` — о том, что отклонил сам до вызова загрузчика: форма не
разбирается (`form_invalid`) или у файла не то расширение (`file_type_invalid`).

```mermaid
sequenceDiagram
    participant Client
    participant API as api (маршрут data)
    participant H as api (единый обработчик ошибок)
    participant Loader as service (загрузчик)
    participant DB as queries (БД)

    alt POST /api/v1/data/upload (multipart: region, tickets_file)
        Client->>API: POST /api/v1/data/upload
        alt тело больше MAX_REQUEST_BODY_BYTES (1 МБ)
            API->>H: исключение предела тела
            H-->>Client: 413 без тела
        else форма не разбирается или сверх пределов (частей больше двух, поле больше 1 КБ)
            API->>API: лог data_upload_failed (warning, reason=form_invalid)
            API->>H: HTTPException 400
            H-->>Client: 400 {message}
        else region не по шаблону или нет поля region / tickets_file
            API->>H: RequestValidationError
            H-->>Client: 400 {fields: [region | tickets_file]}
        else у имени файла расширение не .csv и не .json
            API->>API: лог data_upload_failed (warning, reason=file_type_invalid, region)
            API->>H: InvalidInput(fields: tickets_file)
            H-->>Client: 400 {fields: [tickets_file]}
        else
            API->>Loader: load(region, csv | json, байты файла)
        end
    else POST /api/v1/data/demo {region}
        Client->>API: POST /api/v1/data/demo {"region": "east"}
        alt тело больше MAX_REQUEST_BODY_BYTES
            API->>H: исключение предела тела
            H-->>Client: 413 без тела
        else тело не JSON
            API->>H: RequestValidationError (json_invalid)
            H-->>Client: 400 {message}
        else нет region, region не по шаблону или лишнее поле
            API->>H: RequestValidationError
            H-->>Client: 400 {fields: [region | имя лишнего поля]}
        else
            API->>Loader: load(region, demo)
        end
    end

    alt регион не из конфигурации
        Loader-->>API: InvalidInput(fields: region), лог data_load_failed
        API->>H: InvalidInput
        H-->>Client: 400 {fields: [region]}
    else файл не читается (кодировка, формат, больше 500 заявок или 50 колонок, нет обязательной колонки)
        Loader-->>API: InvalidInput(message), лог data_load_failed
        API->>H: InvalidInput
        H-->>Client: 400 {message}
    else в файле ни одной заявки, которую можно загрузить
        Loader-->>API: InvalidInput(message), лог data_load_failed
        API->>H: InvalidInput
        H-->>Client: 400 {message}
    else БД или включённый внешний геокодер недоступны
        Loader-->>API: DependencyUnavailable, лог data_load_failed (error)
        API->>H: DependencyUnavailable
        H-->>Client: 503 без тела (данные региона не изменились)
    else БД отклонила запрос
        Loader->>DB: замена данных региона (одна транзакция)
        DB-->>Loader: ошибка → ROLLBACK
        Loader-->>API: DatabaseFailure, лог data_load_failed (error)
        API->>H: DatabaseFailure
        H-->>Client: 500 без тела (данные региона не изменились)
    else успех
        Loader->>DB: замена данных региона (одна транзакция)
        Loader-->>API: LoadResult
        API-->>Client: 200 {region, engineers, tickets, rows_total, rows_skipped, rows_invalid[]}
    end
```

## `GET /api/v1/engineers`, `GET /api/v1/tickets`

Списки бригад и заявок одного региона, по возрастанию `id`, без постраничной выдачи: в
регионе не больше 500 заявок (предел файла). Сервис сначала проверяет код по
конфигурации регионов, потом находит id региона в БД по коду и читает строки по `region_id`.
Строк других регионов в ответе не бывает: запрос отбирает строки по id региона. Регион из конфигурации без загруженных
данных — пустой список, не ошибка. Репозиторий переводит геометрию в точку
`{lat, lon}`, время смены — в `ЧЧ:ММ`, окна заявок — в местное время без пояса.
Назначений заявок в списке нет, они в плане. Бизнес-ошибку маршрут логирует как
`list_engineers_failed` / `list_tickets_failed`.

```mermaid
sequenceDiagram
    participant Client
    participant API as api (маршрут engineers | tickets)
    participant H as api (единый обработчик ошибок)
    participant Svc as service
    participant Repo as queries (репозиторий)
    participant DB as PostgreSQL

    Client->>API: GET /api/v1/engineers?region=east | /api/v1/tickets?region=east
    alt region не по шаблону или нет параметра
        API->>H: RequestValidationError
        H-->>Client: 400 {fields: [region]}
    else
        API->>Svc: список (region)
        alt регион не из конфигурации
            Svc-->>API: InvalidInput(fields: region)
            API->>API: лог list_engineers_failed | list_tickets_failed (warning, reason=unknown_region)
            API->>H: InvalidInput
            H-->>Client: 400 {fields: [region]}
        else нет свободного соединения в пуле
            Svc->>Svc: лог db_query_failed (query=list_engineers | list_tickets)
            Svc-->>API: DependencyUnavailable
            API->>API: лог list_engineers_failed | list_tickets_failed (error)
            API->>H: DependencyUnavailable
            H-->>Client: 503 без тела
        else
            Svc->>Repo: id региона по коду
            Repo->>DB: SELECT id FROM regions WHERE code
            alt БД недоступна
                DB-->>Repo: ошибка соединения
                Repo->>Repo: лог db_query_failed
                Repo-->>Svc: DependencyUnavailable
                Svc-->>API: DependencyUnavailable
                API->>API: лог list_engineers_failed | list_tickets_failed (error)
                API->>H: DependencyUnavailable
                H-->>Client: 503 без тела
            else регион не загружен (строки региона нет)
                DB-->>Repo: нет строки
                Repo-->>Svc: None
                Svc-->>API: []
                API-->>Client: 200 []
            else
                Repo->>DB: SELECT ... WHERE region_id ORDER BY id
                DB-->>Repo: строки
                Repo-->>API: модели (Point, время смены, окна)
                API-->>Client: 200 [Engineer] | [Ticket]
            end
        end
    end
```

## `PATCH /api/v1/tickets/{ticket_id}/status`

Диспетчер меняет статус заявки по сообщению бригады. Допустимые переходы:

| Из | В |
|---|---|
| `not_sent` | `sent`, `en_route`, `in_progress`, `completed`, `cancelled`, `overdue` |
| `sent` | `en_route`, `in_progress`, `completed`, `cancelled`, `overdue` |
| `en_route` | `in_progress`, `completed`, `cancelled`, `overdue` |
| `in_progress` | `completed`, `cancelled` |
| `overdue` | `en_route`, `in_progress`, `completed`, `cancelled` |
| `completed`, `cancelled` | — (закрытые статусы) |

Вперёд по цепочке `not_sent → sent → en_route → in_progress → completed` можно и через
шаг: диспетчер отмечает то, о чём сообщила бригада, а промежуточные сообщения могли не
дойти. Назад по цепочке и из закрытого статуса — нельзя: закрытая заявка финальна и в
перепланировании не участвует. Тот же статус, что у заявки уже есть, — `200` без
изменений, так что повтор запроса после обрыва связи безопасен.

Отмена из `en_route` или `in_progress` ставит у заявки `cancelled_after_dispatch`: выезд
бригады уже потрачен и учитывается в метриках плана. Построенные планы операция не меняет.

Чтение статуса, проверка перехода и запись — в одной транзакции, строка заявки
блокируется (`SELECT ... FOR UPDATE`): два одновременных запроса к одной заявке
выполняются по очереди, и второй проверяет переход от статуса, записанного первым.

Изменение сервис логирует после фиксации транзакции событием `ticket_status_changed`
(`ticket_id`, `status_from`, `status_to`); запрос без изменения его не пишет. Отказ маршрут
логирует один раз событием `ticket_status_change_failed` (`ticket_id`, `reason`; при
недопустимом переходе ещё `status_from`, `status_to`).

```mermaid
sequenceDiagram
    participant Client
    participant API as api (маршрут tickets)
    participant H as api (единый обработчик ошибок)
    participant Svc as service (статусы заявок)
    participant Repo as queries (репозиторий)
    participant DB as PostgreSQL

    Client->>API: PATCH /api/v1/tickets/87/status {"status": "completed"}
    alt тело больше MAX_REQUEST_BODY_BYTES
        API->>H: исключение предела тела
        H-->>Client: 413 без тела
    else тело не JSON
        API->>H: RequestValidationError (json_invalid)
        H-->>Client: 400 {message}
    else ticket_id не целое или вне 1..2^63−1, нет status, status не из перечня или лишнее поле
        API->>H: RequestValidationError
        H-->>Client: 400 {fields: [ticket_id | status | имя лишнего поля]}
    else
        API->>Svc: change(ticket_id, status)
        alt нет свободного соединения в пуле или БД недоступна
            Svc->>Svc: лог db_query_failed
            Svc-->>API: DependencyUnavailable
            API->>API: лог ticket_status_change_failed (error)
            API->>H: DependencyUnavailable
            H-->>Client: 503 без тела (статус не изменился)
        else
            Svc->>Repo: BEGIN
            Repo->>DB: SELECT заявка FROM tickets WHERE id FOR UPDATE
            alt заявки нет
                DB-->>Repo: нет строки
                Repo-->>Svc: None → ROLLBACK
                Svc-->>API: NotFound
                API->>API: лог ticket_status_change_failed (warning, reason=ticket_not_found)
                API->>H: NotFound
                H-->>Client: 404 без тела
            else статус уже тот же
                DB-->>Repo: строка заявки
                Repo-->>Svc: Ticket → COMMIT
                Svc-->>API: Ticket (без изменений, без лога)
                API-->>Client: 200 Ticket
            else переход недопустим (назад по цепочке, из закрытого статуса, in_progress → overdue)
                DB-->>Repo: строка заявки
                Svc-->>API: InvalidInput(message) → ROLLBACK
                API->>API: лог ticket_status_change_failed (warning, reason=transition_not_allowed, status_from, status_to)
                API->>H: InvalidInput
                H-->>Client: 400 {message} (статус не изменился)
            else переход допустим
                DB-->>Repo: строка заявки
                Repo->>DB: UPDATE tickets SET status, cancelled_after_dispatch (при отмене из en_route | in_progress) RETURNING ...
                alt БД отклонила запрос
                    DB-->>Repo: ошибка
                    Repo->>Repo: лог db_query_failed → ROLLBACK
                    Repo-->>Svc: DatabaseFailure
                    Svc-->>API: DatabaseFailure
                    API->>API: лог ticket_status_change_failed (error)
                    API->>H: DatabaseFailure
                    H-->>Client: 500 без тела (статус не изменился)
                else
                    DB-->>Repo: строка заявки
                    Repo-->>Svc: Ticket → COMMIT
                    alt COMMIT не удался
                        Svc->>Svc: лог db_query_failed (query=change_ticket_status)
                        Svc-->>API: DependencyUnavailable | DatabaseFailure (без ticket_status_changed)
                        API->>API: лог ticket_status_change_failed (error)
                        API->>H: DependencyUnavailable | DatabaseFailure
                        H-->>Client: 503 | 500 без тела (статус не изменился)
                    else
                        Svc->>Svc: лог ticket_status_changed (ticket_id, status_from, status_to)
                        Svc-->>API: Ticket
                        API-->>Client: 200 Ticket
                    end
                end
            end
        end
    end
```

## `POST /api/v1/plan/build`

Ставит построение плана региона на дату в очередь и отвечает, не дожидаясь его конца:
проверяет заявки и предел точек синхронно, вставляет строку плана со `status = running` и
возвращает её клиенту — чтение открытых заявок и бригад региона, обращение к OSRM, выбранный
алгоритм (`or_tools` — трёхфазная лексикографическая оптимизация в отдельном процессе,
`baseline_fcfs` — в фоновой задаче того же процесса: не блокирует GIL дольше нескольких мс на
максимальном входе), атрибуция причин отказа и запись результата идут в фоновой задаче уже
после ответа. Клиент узнаёт результат, опрашивая `GET /api/v1/plan/{plan_id}`, пока `status`
не станет `done` или `failed`. Каждый вызов создаёт новый план — раньше построенные планы
региона не трогает.

Бизнес-проверки до постановки в очередь: код региона есть в конфигурации и у региона есть
загруженные данные (иначе строить план не по чему); окно каждой открытой заявки региона
приходится на `plan_date` (иначе смены бригад на `plan_date` не совпадают с окнами
заявок, и план не имеет смысла); число точек будущей матрицы (бригады + заявки) не
больше предела OSRM-сервера. Эти проверки — единственное, что может вернуть `400`: сама
постановка в очередь предполагает, что план будет считаться, и вернуться `202` может либо
она, либо отказ БД при вставке строки плана.

Общего дедлайна на всё построение больше нет: раз ответ клиенту уже отправлен, обращение к
OSRM ограничено собственным таймаутом HTTP-клиента, а солвер — своим `time_limit`. Основной
алгоритм выполняется в пуле из одного процесса на весь сервер — конкурентное построение
встаёт в очередь исполнителя, а не запускается параллельно вторым процессом; на очередь эта
операция не отвечает клиенту вообще, поскольку она уже ответила `202` раньше.

Построение логируется `plan_enqueued` (синхронно с ответом `202`) и
`plan_build_finished`/`plan_build_failed` (в фоновой задаче, когда расчёт закончился), оба с
`plan_id`: по нему в логах находятся записи `osrm_request_finished`/`_failed` и
`solver_finished`/`solver_phase_finished` того же построения. Открытые заявки и бригады
региона читаются один раз, при постановке в очередь: фоновая задача получает их напрямую
аргументом, а не читает заново, — только что прочитанные записи не могут разойтись с тем,
что уже проверено бизнес-проверками.

```mermaid
sequenceDiagram
    participant Client
    participant API as api (маршрут plan)
    participant H as api (единый обработчик ошибок)
    participant Svc as service (сборка плана)
    participant Repo as queries (регионы/заявки/бригады)
    participant PlanRepo as queries (планы)
    participant DB as PostgreSQL
    participant BG as фоновая задача
    participant OSRM as client (OSRM)
    participant Pool as отдельный процесс (солвер)
    participant Explain as service (атрибуция и тексты)

    Client->>API: POST /api/v1/plan/build {region, plan_date, algorithm}
    alt тело больше MAX_REQUEST_BODY_BYTES
        API->>H: исключение предела тела
        H-->>Client: 413 без тела
    else тело не JSON, region/plan_date/algorithm нет или не по формату, лишнее поле
        API->>H: RequestValidationError
        H-->>Client: 400 {fields: [...]}
    else
        API->>Svc: enqueue(region, plan_date, algorithm)
        alt region не из конфигурации
            Svc-->>API: InvalidInput(unknown_region)
            API->>H: InvalidInput
            H-->>Client: 400 {fields: [region]}
        else
            Svc->>Repo: region_id региона
            alt у региона нет загруженных данных
                Repo-->>Svc: region_id is None
                Svc-->>API: InvalidInput(region_not_loaded)
                API->>H: InvalidInput
                H-->>Client: 400 {message}
            else
                Repo-->>Svc: region_id
                Svc->>Repo: открытые заявки и бригады региона
                Repo-->>Svc: tickets, engineers
                alt окно хотя бы одной заявки не на plan_date
                    Svc-->>API: InvalidInput(plan_date_mismatch)
                    API->>H: InvalidInput
                    H-->>Client: 400 {message}
                else число точек (бригады + заявки) больше предела OSRM
                    Svc-->>API: InvalidInput(too_many_points)
                    API->>H: InvalidInput
                    H-->>Client: 400 {message}
                else
                    Svc->>PlanRepo: INSERT plans (region_id, plan_date, algorithm, status=running, created_at) RETURNING id
                    alt БД отклонила запрос или недоступна
                        PlanRepo-->>Svc: DependencyUnavailable | DatabaseFailure
                        Svc-->>API: DependencyUnavailable | DatabaseFailure
                        API->>API: лог plan_build_failed (error) → H
                        H-->>Client: 503 | 500 без тела (план не создан)
                    else
                        PlanRepo-->>Svc: plan_id
                        Svc->>Svc: лог plan_enqueued (plan_id, region, algorithm)
                        Svc-->>API: QueuedPlan (plan_id, algorithm, tickets, engineers)
                        API->>BG: build(plan_id, tickets, engineers, plan_date, algorithm)
                        API-->>Client: 202 Plan (plan_id, status=running)
                        par на каждый тип транспорта бригад региона
                            BG->>OSRM: table(vehicle, старты бригад + точки заявок)
                        end
                        alt OSRM недоступен
                            OSRM-->>BG: DependencyUnavailable
                            BG->>PlanRepo: UPDATE plans SET status=failed, failed_reason=osrm_unavailable
                        else матрицы получены
                            OSRM-->>BG: матрицы по типам транспорта
                            alt algorithm = or_tools
                                BG->>Pool: solve_day(tickets, engineers, матрицы, plan_date, time_limit) (единственный процесс на сервер)
                                Pool->>Pool: лог solver_phase_finished ×3, solver_finished
                                Pool-->>BG: DayPlan
                            else algorithm = baseline_fcfs
                                BG->>BG: baseline.solve_day(...) (лог baseline_built)
                            end
                            BG->>Explain: explain(DayPlan, tickets, engineers, матрицы, plan_date)
                            Explain->>Explain: лог unassigned_reason_attributed ×N, unassigned_reasons_summary
                            Explain-->>BG: ExplainedPlan
                            alt построение упало непредвиденно (солвер, explain)
                                BG->>BG: лог plan_build_failed (plan_id, algorithm, error, error)
                                BG->>PlanRepo: UPDATE plans SET status=failed, failed_reason=build_error
                            else
                                BG->>PlanRepo: BEGIN#59; UPDATE plans SET status=done#59; INSERT assignments ×(заявка)#59; COMMIT
                                alt БД отклонила запрос или недоступна
                                    PlanRepo-->>BG: ошибка → ROLLBACK (план остаётся running)
                                    BG->>PlanRepo: UPDATE plans SET status=failed, failed_reason=db_unavailable
                                else
                                    PlanRepo-->>BG: OK
                                    BG->>BG: лог plan_build_finished (plan_id, algorithm)
                                end
                            end
                        end
                    end
                end
            end
        end
    end
```

## `GET /api/v1/plan/{plan_id}`

Читает сохранённую запись плана — без обращения к OSRM или солверу. Ответ
всегда `200 Plan` с полем `status`; клиент отличает состояния по этому полю,
а не по коду ответа:

- `status=running` — построение ещё не завершилось (фоновая задача из
  `POST /plan/build` продолжает работать); `engineers` и `unassigned`
  в ответе отсутствуют.
- `status=done` — построение завершилось успешно; `engineers`, `unassigned`
  и `metrics` заполнены. Маршруты, объяснения и причины неназначенных
  заявок — уже сохранённые данные построения; простой (`idle_time_min`) и
  все поля `metrics` пересчитываются из смены и сохранённых визитов при
  чтении, не хранятся отдельно.
- `status=failed` — построение завершилось ошибкой; заполнено
  `failed_reason`, `engineers` и `unassigned` отсутствуют.

Клиент опрашивает этот эндпоинт с паузой между запросами, пока `status` не
станет `done` или `failed`.

```mermaid
sequenceDiagram
    participant Client
    participant API as api (маршрут plan)
    participant H as api (единый обработчик ошибок)
    participant Svc as service (чтение плана)
    participant PlanRepo as queries (планы)
    participant DB as PostgreSQL

    Client->>API: GET /api/v1/plan/42
    alt plan_id не целое или вне 1..2^63−1
        API->>H: RequestValidationError
        H-->>Client: 400 {fields: [plan_id]}
    else
        API->>Svc: get(plan_id)
        Svc->>PlanRepo: план, его статус и (если есть) назначения и бригады региона
        alt нет свободного соединения в пуле или БД недоступна
            PlanRepo->>PlanRepo: лог db_query_failed
            PlanRepo-->>Svc: DependencyUnavailable
            Svc->>Svc: лог plan_get_failed (error)
            Svc-->>API: DependencyUnavailable
            API->>H: DependencyUnavailable
            H-->>Client: 503 без тела
        else плана с таким id нет
            PlanRepo-->>Svc: None
            Svc->>Svc: лог plan_get_failed (warning, reason=plan_not_found)
            Svc-->>API: NotFound
            API->>H: NotFound
            H-->>Client: 404 без тела
        else status=running
            PlanRepo-->>Svc: план (status=running), без назначений
            Svc-->>API: Plan (status=running, без engineers и unassigned)
            API-->>Client: 200 Plan
        else status=failed
            PlanRepo-->>Svc: план (status=failed, failed_reason)
            Svc-->>API: Plan (status=failed, без engineers и unassigned)
            API-->>Client: 200 Plan
        else status=done
            PlanRepo-->>Svc: план (status=done), назначения, бригады региона
            Svc->>Svc: собрать маршруты (idle_time_min из смены и визитов) и metrics из них, без лога
            Svc-->>API: Plan (status=done, engineers, unassigned, metrics)
            API-->>Client: 200 Plan
        end
    end
```

## `GET /api/v1/plan/{plan_id}/compare`

Сравнивает `metrics` двух планов (`plan_id` из пути и `baseline_plan_id` из
query) по каждой обязательной метрике — `engineers_used`, `total_distance_km`
— и отвечает разницей. Оба плана читаются тем же методом, что отвечает на
`GET /api/v1/plan/{plan_id}` (`Svc.get`), по одному за раз: сперва `plan_id`,
и только если он готов — `baseline_plan_id`, так что проблема с главным
планом никогда не трогает baseline вовсе. План не готов к сравнению, если у
него ещё нет `metrics` (`status` не `done`). Разница считается тем же
сервисом, а не маршрутом — маршрут только переводит доменный результат в
контракт.

```mermaid
sequenceDiagram
    participant Client
    participant API as api (маршрут plan)
    participant H as api (единый обработчик ошибок)
    participant Svc as service (чтение плана)
    participant PlanRepo as queries (планы)
    participant DB as PostgreSQL

    Client->>API: GET /api/v1/plan/42/compare?baseline_plan_id=41
    alt plan_id или baseline_plan_id не целое или вне 1..2^63−1
        API->>H: RequestValidationError
        H-->>Client: 400 {fields: [plan_id | baseline_plan_id]}
    else
        API->>Svc: compare(plan_id, baseline_plan_id)
        Svc->>Svc: get(plan_id)
        Svc->>PlanRepo: план, его статус и (если есть) назначения и бригады региона
        alt нет свободного соединения в пуле или БД недоступна
            PlanRepo->>PlanRepo: лог db_query_failed
            PlanRepo-->>Svc: DependencyUnavailable
            Svc-->>API: DependencyUnavailable
            API->>API: лог plan_compare_failed (error, plan_id, baseline_plan_id)
            API->>H: DependencyUnavailable
            H-->>Client: 503 без тела
        else плана plan_id нет
            PlanRepo-->>Svc: None
            Svc-->>API: NotFound
            API->>API: лог plan_compare_failed (warning, reason=plan_not_found)
            API->>H: NotFound
            H-->>Client: 404 без тела
        else status plan_id не done
            PlanRepo-->>Svc: план (status=running|failed)
            Svc-->>API: InvalidInput(plan_not_ready) — baseline_plan_id не читается вовсе
            API->>API: лог plan_compare_failed (warning, reason=plan_not_ready)
            API->>H: InvalidInput
            H-->>Client: 400 {message}
        else
            Svc->>Svc: get(baseline_plan_id) — та же последовательность ветвлений, что и для plan_id
            alt baseline_plan_id не готов так же, как выше
                Svc-->>API: DependencyUnavailable | NotFound | InvalidInput(plan_not_ready)
                API->>API: лог plan_compare_failed
                API->>H: та же ошибка
                H-->>Client: 503 | 404 | 400
            else оба плана done
                Svc->>Svc: [engineers_used, total_distance_km] с delta = main − baseline
                Svc-->>API: (PlanComparisonEntry, PlanComparisonEntry)
                API-->>Client: 200 [PlanComparisonEntry, PlanComparisonEntry]
            end
        end
    end
```
