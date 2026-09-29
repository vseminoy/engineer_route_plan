# Тесты общего формата ошибок полей (`front/src/lib/`)

## Содержание

- [`src/lib/fieldErrors.ts` — один формат ошибок полей](#srclibfielderrorsts--один-формат-ошибок-полей)
- [`src/lib/fileValidation.ts` — проверка файла заявок](#srclibfilevalidationts--проверка-файла-заявок)
- [`src/lib/labels.ts` — текст ошибки по операции и коду](#srcliblabelsts--текст-ошибки-по-операции-и-коду)

---

## `src/lib/fieldErrors.ts` — один формат ошибок полей

Файл: `src/lib/fieldErrors.test.ts` (`vitest`).

| Test | Scenario | Expected result |
|---|---|---|
| `names a nested array field the way the spec does` | zod проверяет `{ engineers: [{ skills: 1 }] }` против схемы со строковым `skills` | ключ ошибки — `engineers[0].skills` |
| `give the same record for the same field name` | одно и то же имя параметра (`region`) приходит и из zod-issue, и из `fields` ответа `400` | оба источника дают запись с одинаковым именем поля |

## `src/lib/fileValidation.ts` — проверка файла заявок

Файл: `src/lib/fileValidation.test.ts` (`vitest`).

| Test | Scenario | Expected result |
|---|---|---|
| `rejects an unsupported extension` | Файл `tickets.txt` | Текст «Поддерживаются только файлы .csv или .json.» |
| `rejects an empty file` | Файл `tickets.csv` размером 0 байт | Текст «Файл пустой.» |
| `rejects a file over the backend size limit` | Файл размером `MAX_UPLOAD_BYTES + 1` | Текст «Файл слишком большой (предел — 1 МБ).» |
| `accepts a non-empty .csv or .json file within the limit` | Файлы `tickets.csv` (ровно на пределе) и `TICKETS.JSON` | `null` (файл проходит проверку) |

## `src/lib/labels.ts` — текст ошибки по операции и коду

Файл: `src/lib/labels.test.ts` (`vitest`).

| Test | Scenario | Expected result |
|---|---|---|
| `uses the operation-specific text for a 404 on ticket status change` | `describeError` для `ApiError(404)` с `endpoint: 'PATCH /tickets/{id}/status'` | Текст «Заявка не найдена», а не общий текст `404` |
