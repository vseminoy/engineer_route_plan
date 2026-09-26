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
