# Sequence-диаграммы — `src/clients/`

## Время и расстояние в пути (OSRM)

Клиент OSRM даёт планировщику две вещи: матрицу «время / расстояние в пути» между точками
(`/table`) и маршрут через последовательность точек с геометрией для карты (`/route`). Оба
считаются только по графу дорог; прямая между точками не используется ни как основной
способ, ни как запасной. Своей операции API у клиента нет: его вызывают построение плана и
перепланирование, а отказ OSRM они отдают как `503` по общей схеме ошибок.

**Профиль транспорта бригады → граф.** Каждый из `car`, `foot`, `bike` — свой граф дорог и
свой экземпляр `osrm-routed` (URL в настройках: `OSRM_URL_CAR`, `OSRM_URL_FOOT`,
`OSRM_URL_BIKE`): один `osrm-routed` обслуживает ровно один профиль, профиль в пути
запроса он не читает. `public_transport` своего графа не имеет: время — время профиля
`car`, умноженное на коэффициент `PUBLIC_TRANSPORT_FACTOR` (по умолчанию 1,5, не меньше
1), расстояние — расстояние `car` без изменений. Коэффициент — усреднённая оценка
пересадок, ожиданий и пешей части пути, а не расчёт маршрута общественного транспорта.

**Единицы и порядок координат.** Ответ клиента — секунды и метры, как у OSRM (дробные);
округление до минут — дело планировщика. Точка — `Point(lat, lon)`; в URL OSRM
координаты идут в порядке `lon,lat`, с пятью знаками после запятой (около метра). Строка
и столбец матрицы `i` — точка `i` входного списка.

**Нет маршрута между парой точек** (точки в несвязанных частях графа): ячейка матрицы —
`None`, для `/route` — результат `None`. Клиент не подставляет вместо неё ни прямую, ни
ноль: переход между такими точками для планировщика невозможен.

**Размер матрицы.** `osrm-routed` отклоняет таблицу, у которой источников × назначений
больше квадрата его `--max-table-size` (на стенде — 1000, в настройках клиента
`OSRM_MAX_TABLE_SIZE` — то же значение). Если точек больше, клиент запрашивает матрицу
полосами строк: все точки — назначения, в полосе столько источников, чтобы произведение
укладывалось в предел; полосы склеиваются по порядку. Пустой список точек — пустая
матрица, одна точка — матрица `[[0]]`, обе без запроса: таблицу из одной точки
`osrm-routed` отклоняет. Точек в матрице дня — заявки файла (не больше 500) и старты
бригад региона (не больше 30): до 530 точек, один запрос с URL около 10 КБ.

**Отказ OSRM.** Сетевая ошибка, таймаут (`OSRM_TIMEOUT_S`, по умолчанию 60 с на запрос:
матрица из 530 точек на графе `bike` считается до ~26 с), URL длиннее предела HTTP-клиента, код
ответа не 200 или `code` в теле не `Ok`, тело без ожидаемых полей или с числом не того
вида (не число, бесконечность, `NaN`), матрица или маршрут не того размера (у маршрута
участков на один меньше, чем точек, в геометрии не меньше двух точек) —
`DependencyUnavailable(reason="osrm_unavailable")`, одна запись `osrm_request_failed` на
месте; отвергнутый ответ не пишется как выполненный запрос. Единственное исключение — `NoRoute` у `/route`: это не
отказ, а «нет маршрута» (см. выше). Отказ одного профиля (граф `foot` ещё строится) не
затрагивает запросы других профилей. Ответ полосы, пришедший с ошибкой, отменяет весь
запрос матрицы: неполная матрица не возвращается.

**Логи.** `osrm_request_finished` (`debug`) и `osrm_request_failed` (`error`) — одна из двух на
каждый HTTP-запрос к OSRM, с полями `endpoint` (`table`/`route`), `profile` (граф, в
который ушёл запрос), `points`, `status`, `duration_ms`; при отказе ещё `error`: класс
исключения, `code` из тела, `http_error` (код не 200 и тело не JSON) или
`malformed_response`. Координат в записях нет: точка заявки — это адрес клиента.

```mermaid
sequenceDiagram
    autonumber
    participant S as service (планировщик)
    participant C as client OsrmClient
    participant O as osrm-routed (граф профиля)

    Note over S,C: table(vehicle, points) → TravelMatrix(durations_s, distances_m)
    S->>C: table(vehicle, points)
    alt points пуст или одна точка
        C-->>S: [] или [[0]] (без запроса)
    end
    C->>C: vehicle → граф: car/foot/bike — свой URL,<br/>public_transport — граф car, factor = PUBLIC_TRANSPORT_FACTOR
    C->>C: полосы источников: len(полосы) × len(points) ≤ OSRM_MAX_TABLE_SIZE²
    loop по полосам, по порядку
        C->>O: GET /table/v1/{profile}/{lon,lat#59;…}?sources=…&annotations=duration,distance
        alt сеть, таймаут OSRM_TIMEOUT_S, URL длиннее предела клиента
            O--xC: ошибка соединения (или запрос не отправлен)
            C->>C: лог osrm_request_failed (endpoint=table, profile, points, error)
            C-->>S: DependencyUnavailable(osrm_unavailable)
        else код ≠ 200 или code ≠ Ok (в т.ч. TooBig, NoSegment)
            O-->>C: ответ с ошибкой
            C->>C: лог osrm_request_failed (status, error=code или http_error)
            C-->>S: DependencyUnavailable(osrm_unavailable)
        else 200, но нет durations/distances, размер не тот, ячейка не число или не конечна
            O-->>C: 200 {code: Ok, …}
            C->>C: лог osrm_request_failed (status=200, error=malformed_response)
            C-->>S: DependencyUnavailable(osrm_unavailable)
        else 200, code = Ok
            O-->>C: durations[][], distances[][] (null — нет маршрута)
            C->>C: лог osrm_request_finished (debug)
        end
    end
    C->>C: склейка полос, null → None,<br/>public_transport: durations × factor
    C-->>S: TravelMatrix (секунды, метры)

    Note over S,C: route(vehicle, points) → Route(duration_s, distance_m, legs, geometry) | None
    S->>C: route(vehicle, points ≥ 2)
    C->>C: vehicle → граф (как у table)
    C->>O: GET /route/v1/{profile}/{lon,lat#59;…}?overview=full&geometries=geojson
    alt сеть, таймаут, код ≠ 200 и code ≠ NoRoute, тело без routes/geometry,<br/>участков ≠ точек − 1, в геометрии меньше 2 точек, число не того вида
        C->>C: лог osrm_request_failed (endpoint=route, …)
        C-->>S: DependencyUnavailable(osrm_unavailable)
    else code = NoRoute
        O-->>C: 400 {code: NoRoute}
        C->>C: лог osrm_request_finished (debug, found=false)
        C-->>S: None, маршрута нет
    else 200, code = Ok
        O-->>C: routes[0]: duration, distance, legs[], geometry (GeoJSON lon,lat)
        C->>C: geometry → [Point(lat, lon)],<br/>public_transport: duration и legs[].duration × factor
        C-->>S: Route
    end
```
