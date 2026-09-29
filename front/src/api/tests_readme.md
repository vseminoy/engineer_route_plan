# Тесты HTTP-клиента фронтенда (`front/src/api/`)

## Содержание

- [`src/api/client.ts` — разбор ответа с ошибкой](#srcapiclientts--разбор-ответа-с-ошибкой)
- [`src/api/mappers.ts` — маппинг сгенерированных типов в доменные](#srcapimappersts--маппинг-сгенерированных-типов-в-доменные)
- [`src/api/mappers.ts` — `mapPlanCompare`](#srcapimappersts--mapplancompare)
- [`src/api/mappers.ts` — `mapPlanReplanResult`](#srcapimappersts--mapplanreplanresult)
- [`src/api/mappers.ts` — `mapEngineerSet`](#srcapimappersts--mapengineerset)
- [`src/api/endpoints.ts` — `setTicketStatus`](#srcapiendpointsts--setticketstatus)
- [`src/api/endpoints.ts` — `replan`](#srcapiendpointsts--replan)
- [`src/api/endpoints.ts` — наборы бригад региона](#srcapiendpointsts--наборы-бригад-региона)

---

## `src/api/client.ts` — разбор ответа с ошибкой

Файл: `src/api/client.test.ts` (`vitest`).

> Замена стабами: глобальный `fetch` (`vi.stubGlobal`) — возвращает `Response` с нужным
> статусом, телом и заголовками, либо реджектится (сетевая ошибка); настоящий backend не нужен.

| Test | Scenario | Expected result |
|---|---|---|
| `400 with message keeps it, with no field errors` | `fetch` отвечает `400` с телом `{"message": "..."}` | `ApiError.body` — не `FieldErrors` (`isFieldErrors` false), `message` из тела |
| `400 with fields carries one entry per field` | `fetch` отвечает `400` с телом `{"fields": [...]}` | `ApiError.body.fields` — тот же массив, `isFieldErrors` true |
| `%i has no body to parse` (`404`, `501`, `503`) | `fetch` отвечает без тела | `ApiError` с этим `status`, `body === undefined` |
| `carries the X-Request-ID header` | `fetch` отвечает `500` с заголовком `X-Request-ID` | `ApiError.requestId` равен значению заголовка |
| `a fetch that never reaches the server throws NetworkError` | `fetch` реджектится (`TypeError`) | `http.get` бросает `NetworkError`, а не `ApiError` |
| `successful response is returned as JSON` | `fetch` отвечает `200` с телом `[]` | `http.get` возвращает `[]` |

## `src/api/mappers.ts` — маппинг сгенерированных типов в доменные

Файл: `src/api/mappers.test.ts` (`vitest`).

| Test | Scenario | Expected result |
|---|---|---|
| `flattens the start point and converts shift bounds to minutes since midnight` | `mapEngineerRoster` на бригаде со `start: {lat, lon}` и сменой `'08:00'`–`'20:00'` | `startLat`/`startLon` — из `start`, `shiftStartMin`/`shiftEndMin` — минуты с полуночи |
| `carries the numeric priority rank and derives the window in minutes from the naive datetime` | `mapTicketSummary` на заявке с `priority: 1` и `window_start`/`window_end` — полным наивным datetime | `priority` — то же число, `windowStartMin`/`windowEndMin` — минуты с полуночи выбранного дня |
| `translates snake_case counts and invalid rows into the domain shape` | `mapDataLoadResult` на ответе с `rows_invalid` | доменный `DataLoadResult` с `engineersCount`/`ticketsCount`/`rowsTotal`/`rowsSkipped`/`invalidRows` |
| `maps a running build to a status with no engineers/unassigned/metrics yet` | `mapPlan` на `{status: 'running'}` | `Plan` без `engineers`/`unassigned`/`metrics`/`failedReason` |
| `maps a failed build to its reason, with no engineers/unassigned/metrics` | `mapPlan` на `{status: 'failed', failed_reason: 'osrm_unavailable'}` | `Plan` с `failedReason`, без `engineers`/`unassigned`/`metrics` |
| `maps a failed build stopped by the server-shutdown sweep` | `mapPlan` на `{status: 'failed', failed_reason: 'shutdown'}` | `failedReason` равен `'shutdown'` |
| `maps engineers/unassigned/metrics straight from the API response when done, keeping the naive arrival time as-is` | `mapPlan` на `{status: 'done', engineers: [...], unassigned: [...], metrics: {...}}` (сервер теперь всегда присылает `metrics`) | `metrics` — прямой camelCase-маппинг присланного объекта, без клиентского пересчёта; `plannedArrival` — та же строка без сдвига |

## `src/api/mappers.ts` — `mapPlanCompare`

Файл: `mappers.test.ts` (`vitest`), там же, где остальные мапперы.

| Test | Scenario | Expected result |
|---|---|---|
| `reshapes the compare_plan entries into the fixed engineersUsed/totalDistanceKm pair` | Массив `PlanComparisonEntry` из двух записей (`engineers_used`, `total_distance_km`) | Доменный `PlanCompare` — `{main, baseline, delta}` для каждой из двух метрик |
| `throws if the response is missing a mandatory metric` | Массив с одной записью (`total_distance_km` отсутствует) | Функция бросает исключение — ответ backend, отступающий от контракта, не должен тихо превратиться в `undefined` |

## `src/api/mappers.ts` — `mapPlanReplanResult`

Файл: `mappers.test.ts` (`vitest`), там же, где остальные мапперы.

| Test | Scenario | Expected result |
|---|---|---|
| `maps the synchronous replan response to a done plan with its diff` | `PlanReplanResult` с `parent_plan_id`, метриками и `diff` | Доменный `Plan` — `status: 'done'`, `parentPlanId`, метрики и `diff` замаплены напрямую |

## `src/api/mappers.ts` — `mapEngineerSet`

Файл: `mappers.test.ts` (`vitest`), там же, где остальные мапперы.

| Test | Scenario | Expected result |
|---|---|---|
| `translates the generator parameters to camelCase, keeping the display description as-is` | `EngineerSet` из `GET /engineer-sets` с `morning_share`/`evening_share` и `description` | Доменный `EngineerSet` — camelCase-поля генератора, `description` без изменений |

## `src/api/endpoints.ts` — `setTicketStatus`

Файл: `src/api/endpoints.test.ts` (`vitest`), тот же приём со стабом глобального `fetch`, что и у `client.test.ts` — `changeTicketStatus` (сгенерированный клиент) ходит через него же.

| Test | Scenario | Expected result |
|---|---|---|
| `maps the 200 response to the domain ticket summary` | `fetch` отвечает `200` с заявкой | `setTicketStatus` возвращает `TicketSummary`, замапленную из ответа |
| `rejects an invalid transition with the 400 message as-is` | `fetch` отвечает `400` с `{"message": "..."}` (недопустимый переход) | `ApiError` с этим `message`, статус заявки не считается изменённым |
| `rejects a missing ticket with a bodyless 404` | `fetch` отвечает `404` без тела | `ApiError` со статусом `404` и `body === undefined` |

## `src/api/endpoints.ts` — `replan`

Файл: `src/api/endpoints.test.ts` (`vitest`), тот же приём со стабом глобального `fetch` — `replanPlan` (сгенерированный клиент) ходит через него же.

| Test | Scenario | Expected result |
|---|---|---|
| `maps the synchronous 200 response to a done plan with its diff` | `fetch` отвечает `200` готовым планом | `replan` возвращает `Plan` со `status: 'done'` и `parentPlanId` из ответа |
| `rejects an invalid field with a 400 fields response` | `fetch` отвечает `400` с `{"fields": [...]}` | `ApiError.body.fields` — тот же массив |
| `rejects a cancel event for a ticket not yet cancelled with a bodyless 409` | `fetch` отвечает `409` без тела | `ApiError` со статусом `409` и `body === undefined` |

## `src/api/endpoints.ts` — наборы бригад региона

Файл: `src/api/endpoints.test.ts` (`vitest`), тот же приём со стабом глобального `fetch` — `listEngineerSets`/`createEngineerSet`/`deleteEngineerSet` (сгенерированный клиент) ходят через него же.

| Test | Scenario | Expected result |
|---|---|---|
| `maps the array response to domain engineer sets` | `fetch` отвечает `200` списком наборов | `getEngineerSets` возвращает массив доменных `EngineerSet` |
| `maps the 201 response to a domain engineer set` | `fetch` отвечает `201` созданным набором | `createEngineerSet` возвращает доменный `EngineerSet` |
| `rejects a duplicate name in the region with a bodyless 409` | `fetch` отвечает `409` без тела | `ApiError` со статусом `409` и `body === undefined` |
| `resolves on a bodyless 204` | `fetch` отвечает `204` без тела | `deleteEngineerSet` резолвится в `undefined` |
| `rejects deleting the default set with a bodyless 409` | `fetch` отвечает `409` без тела | `ApiError` со статусом `409` и `body === undefined` |
