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
