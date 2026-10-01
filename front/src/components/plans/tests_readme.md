# Тесты списка сгенерированных планов (`front/src/components/plans/`)

## Содержание

- [`PlansScreen` — список планов региона](#plansscreen--список-планов-региона)
- [`PlanDeleteConfirm` — подтверждение удаления плана](#plandeleteconfirm--подтверждение-удаления-плана)
- [`PlanRenameModal` — переименование плана](#planrenamemodal--переименование-плана)

---

## `PlansScreen` — список планов региона

Файл: `PlansScreen.test.tsx` (`vitest` + `@testing-library/react`, `QueryClientProvider`,
`MemoryRouter`).

> `useRegions` замокан (встроенный список регионов, без сети); `getPlans`/`deletePlan`/
> `renamePlan` (`api/endpoints`) замоканы; `useNavigate` замокан, чтобы проверять переход
> по клику на строку без реального роутинга.

| Test | Scenario | Expected result |
|---|---|---|
| `prompts for a region before showing any plans` | Регион не выбран | Текст «Выберите регион, чтобы увидеть его планы.»; `getPlans` не вызван |
| `lists the region's plans once loaded, by their name` | Выбран регион, `getPlans` вернул один план (`status: 'done', name: 'Утренний обход'`) | Виден текст «Утренний обход» (не «План №42») и статус «Готов»; `getPlans` вызван с `('east', null)` |
| `shows an empty-state message when the region has no plans` | `getPlans` вернул `[]` | Текст «У этого региона ещё нет построенных планов.» |
| `opens the plan on a row click` | Клик по строке плана | `navigate` вызван с `/plan/42` |
| `opens the delete confirmation without navigating when its button is clicked` | Клик по кнопке «Удалить» строки | Виден диалог `PlanDeleteConfirm` («Удалить план №42?»); `navigate` не вызван |
| `removes the deleted plan from the list` | Подтверждено удаление в диалоге | `deletePlan` вызван с `42`; после инвалидации списка строка плана исчезает |
| `opens the rename modal without navigating when its button is clicked, whatever the plan's status or algorithm` | Клик по кнопке «Переименовать» строки плана в статусе `running`/`baseline_fcfs` | Виден диалог `PlanRenameModal` с текущим названием; `navigate` не вызван |
| `shows the new name in the list right after a successful rename, without refetching` | В открытом диалоге введено новое название и подтверждено | Строка списка показывает новое название; `getPlans` не вызывается повторно |

## `PlanDeleteConfirm` — подтверждение удаления плана

Файл: `PlanDeleteConfirm.test.tsx` (`vitest` + `@testing-library/react`, `QueryClientProvider`).

> `deletePlan` (`api/endpoints`) замокан.

| Test | Scenario | Expected result |
|---|---|---|
| `warns that replans made from this plan are deleted with it` | Диалог открыт | Виден текст «Все перепланирования, сделанные от этого плана, тоже будут удалены.» |
| `deletes the plan and reports it to the parent` | Нажата «Удалить» | `deletePlan` вызван с `planId`, `onDeleted` вызван |
| `shows the dictionary message when the plan is already gone (404)` | `deletePlan` реджектится `ApiError(404)` | Текст «План уже удалён» |
| `shows the dictionary message when the plan is still running (409)` | `deletePlan` реджектится `ApiError(409)` | Текст «План ещё строится — подождите и попробуйте снова» |

## `PlanRenameModal` — переименование плана

Файл: `PlanRenameModal.test.tsx` (`vitest` + `@testing-library/react`, `QueryClientProvider`).

> `renamePlan` (`api/endpoints`) замокан; валидация — настоящей zod-схемой `PlanRenameRequest`
> (сгенерированной), как в `EngineerSetCreateForm`.

| Test | Scenario | Expected result |
|---|---|---|
| `shows the plan's current name pre-filled in the input` | Диалог открыт для плана с `name: 'План №42'` | Поле ввода содержит `'План №42'` |
| `rejects an empty name (after trimming) before sending the request` | Поле очищено до одних пробелов, нажата «Переименовать» | Ошибка схемы под полем, `renamePlan` не вызван |
| `rejects a name longer than 100 characters before sending the request` | Введено 101-символьное название, нажата «Переименовать» | Ошибка схемы под полем, `renamePlan` не вызван |
| `renames the plan and reports the new summary to the parent` | Введено корректное название, нажата «Переименовать» | `renamePlan` вызван с `(42, трим-названием)`; `onRenamed` вызван с ответом `renamePlan` |
| `shows the field error from the 400 response when the server rejects it` | `renamePlan` реджектится `ApiError(400, {fields: [{name: 'name', message: '...'}]})` | То же сообщение показано под полем (`fieldErrorsFromApi`) |
| `shows the dictionary message when the plan is already gone (404)` | `renamePlan` реджектится `ApiError(404)` | Текст «План уже удалён» |
