# Тесты HTTP-клиента фронтенда (`front/src/api/`)

## Содержание

- [`src/api/client.ts` — разбор ответа с ошибкой](#srcapiclientts--разбор-ответа-с-ошибкой)

---

## `src/api/client.ts` — разбор ответа с ошибкой

Файл: `src/api/client.test.ts` (`vitest`).

> Замена стабами: глобальный `fetch` (`vi.stubGlobal`) — возвращает `Response` с нужным
> статусом и телом; настоящий backend не нужен.

| Test | Scenario | Expected result |
|---|---|---|
| `501 without body → "not implemented" message` | `fetch` отвечает `501` с пустым телом (`statusText: "Not Implemented"`) | `http.get` бросает `ApiError` со `status === 501` и `message === "Эта функция ещё не реализована"`, а не английский `statusText` |
| `error with JSON body keeps its message` | `fetch` отвечает `404` с телом `{"error_code": "PLAN_NOT_FOUND", "message": "..."}` | `ApiError` с `errorCode === "PLAN_NOT_FOUND"` и `message` из тела — разбор тела не изменился |
| `other status without body falls back to statusText` | `fetch` отвечает `503` с пустым телом, `statusText: "Service Unavailable"` | `ApiError` со `status === 503`, `errorCode === "UNKNOWN"`, `message === "Service Unavailable"` — отдельный текст только у `501` |
| `successful response is returned as JSON` | `fetch` отвечает `200` с телом `[]` | `http.get` возвращает `[]` |
