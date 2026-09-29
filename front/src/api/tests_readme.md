# Тесты HTTP-клиента фронтенда (`front/src/api/`)

## Содержание

- [`src/api/client.ts` — разбор ответа с ошибкой](#srcapiclientts--разбор-ответа-с-ошибкой)
- [`src/api/mappers.ts` — маппинг сгенерированных типов в доменные](#srcapimappersts--маппинг-сгенерированных-типов-в-доменные)

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
