# Тесты экрана загрузки данных (`front/src/components/dataload/`)

## Содержание

- [`FileUploadForm` — валидация файла заявок](#fileuploadform--валидация-файла-заявок)
- [`RegionSelect` — отображение ошибки поля и `onBlur`](#regionselect--отображение-ошибки-поля-и-onblur)
- [`EngineerSetSelect` — выбор и удаление набора](#engineersetselect--выбор-и-удаление-набора)
- [`EngineerSetCreateForm` — валидация формы создания набора](#engineersetcreateform--валидация-формы-создания-набора)
- [`EngineerSetDeleteConfirm` — подтверждение удаления набора](#engineersetdeleteconfirm--подтверждение-удаления-набора)
- [`DataLoadScreen` — `503`/`500` на самом `POST /plan/build`](#dataloadscreen--503500-на-самом-post-planbuild)

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

## `EngineerSetSelect` — выбор и удаление набора

Файл: `EngineerSetSelect.test.tsx` (`vitest` + `@testing-library/react`).

> `useEngineerSets` замокан — список наборов задаётся напрямую, без сети.

| Test | Scenario | Expected result |
|---|---|---|
| `offers only the default option and no delete button when the region has no extra sets` | Регион только с набором `kind: 'demo'` | В селекте один пункт «По умолчанию», кнопки «Удалить набор» нет |
| `reports the chosen set id, and null back for the default set` | Выбран пункт дополнительного набора, затем — пункт по умолчанию | `onChange` вызван с `id` набора, затем с `null` |
| `shows a delete button for the selected generated set and reports it on click` | Выбран дополнительный набор (`kind: 'generated'`), нажата «Удалить набор» | `onDeleteClick` вызван с этим набором |

## `EngineerSetCreateForm` — валидация формы создания набора

Файл: `EngineerSetCreateForm.test.tsx` (`vitest` + `@testing-library/react`, `QueryClientProvider`).

> `createEngineerSet` (`api/endpoints`) замокан — проверяется валидация сгенерированной
> zod-схемой `POST /engineer-sets` до отправки и разбор ответа/ошибки после.

| Test | Scenario | Expected result |
|---|---|---|
| `rejects an empty name and seed before sending the request` | Не заполнены название и seed | Текст ошибки под обоими полями, запрос не отправлен |
| `rejects a shift share out of the 0–1 range before sending the request` | Доля вечерней смены — `1.5` | Текст ошибки под полем, запрос не отправлен |
| `sends a valid form and reports the created set to the parent` | Все поля валидны | `createEngineerSet` вызван с телом запроса, `onCreated` — с созданным набором |
| `shows the dictionary message on a duplicate name (409)` | `createEngineerSet` реджектится `ApiError(409)` | Текст «Набор с таким названием уже есть в регионе» |

## `EngineerSetDeleteConfirm` — подтверждение удаления набора

Файл: `EngineerSetDeleteConfirm.test.tsx` (`vitest` + `@testing-library/react`, `QueryClientProvider`).

> `deleteEngineerSet` (`api/endpoints`) замокан.

| Test | Scenario | Expected result |
|---|---|---|
| `warns that the set's plans are deleted with it` | Диалог открыт | Виден текст «Планы этого набора тоже будут удалены.» |
| `deletes the set and reports it to the parent` | Нажата «Удалить» | `deleteEngineerSet` вызван с `id` набора, `onDeleted` вызван |
| `shows the dictionary message when the set is already gone (404)` | `deleteEngineerSet` реджектится `ApiError(404)` | Текст «Набор уже удалён» |

## `DataLoadScreen` — `503`/`500` на самом `POST /plan/build`

Файл: `DataLoadScreen.test.tsx` (`vitest` + `@testing-library/react`, `QueryClientProvider`).

> `loadDemoDataset`/`buildPlan` (`api/endpoints`) замоканы — проверяется реакция экрана на
> отказ построения плана, который сам загрузчик данных запускает сразу после чистой
> загрузки, а не сеть.

| Test | Scenario | Expected result |
|---|---|---|
| `shows a full-screen retry notice on a 503 from the build that follows a clean demo load` | Демо-набор загрузился без ошибок, `buildPlan` реджектится `ApiError(503)` | `FullScreenErrorNotice` с текстом по словарю и кнопкой «Повторить» |
