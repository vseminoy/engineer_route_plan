# Тесты экрана загрузки данных (`front/src/components/dataload/`)

## Содержание

- [`FileUploadForm` — валидация файла заявок](#fileuploadform--валидация-файла-заявок)
- [`RegionSelect` — отображение ошибки поля и `onBlur`](#regionselect--отображение-ошибки-поля-и-onblur)

---

## `FileUploadForm` — валидация файла заявок

Файл: `FileUploadForm.test.tsx` (`vitest` + `@testing-library/react`).

> Тестовая обёртка сама держит `error` и передаёт его назад в `FileUploadForm` — так же,
> как `DataLoadScreen` ведёт карту ошибок полей (F2); это проверяет полный круг «выбор
> файла → сообщение под полем», а не только аргументы колбэка.

| Test | Scenario | Expected result |
|---|---|---|
| `rejects an unsupported extension under the field, before submit` | Выбран файл `tickets.txt` | Текст ошибки под полем, кнопка отправки недоступна |
| `rejects an empty file under the field` | Выбран пустой файл `tickets.csv` | Текст «Файл пустой.» под полем |
| `accepts a valid file, enables submit, and passes the file through` | Выбран валидный `tickets.csv`, нажата кнопка | Кнопка доступна, `onSubmit` вызван с этим файлом |

## `RegionSelect` — отображение ошибки поля и `onBlur`

Файл: `RegionSelect.test.tsx` (`vitest` + `@testing-library/react`).

> `useRegions` замокан (данные не нужны — используется встроенный список регионов),
> чтобы тест не обращался к сети.

| Test | Scenario | Expected result |
|---|---|---|
| `shows the field error passed by the parent` | Передан `error="Некорректный регион"` | Текст ошибки виден под селектом |
| `fires onBlur so the parent can (re)validate the region field` | Потеря фокуса селектом | `onBlur` вызван один раз |
