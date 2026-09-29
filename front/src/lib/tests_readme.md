# Тесты общего формата ошибок полей (`front/src/lib/`)

## Содержание

- [`src/lib/fieldErrors.ts` — один формат ошибок полей](#srclibfielderrorsts--один-формат-ошибок-полей)

---

## `src/lib/fieldErrors.ts` — один формат ошибок полей

Файл: `src/lib/fieldErrors.test.ts` (`vitest`).

| Test | Scenario | Expected result |
|---|---|---|
| `names a nested array field the way the spec does` | zod проверяет `{ engineers: [{ skills: 1 }] }` против схемы со строковым `skills` | ключ ошибки — `engineers[0].skills` |
| `give the same record for the same field name` | одно и то же имя параметра (`region`) приходит и из zod-issue, и из `fields` ответа `400` | оба источника дают запись с одинаковым именем поля |
