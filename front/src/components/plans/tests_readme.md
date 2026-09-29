# Тесты списка сгенерированных планов (`front/src/components/plans/`)

## Содержание

- [`PlansScreen` — список планов региона](#plansscreen--список-планов-региона)
- [`PlanDeleteConfirm` — подтверждение удаления плана](#plandeleteconfirm--подтверждение-удаления-плана)

---

## `PlansScreen` — список планов региона

Файл: `PlansScreen.test.tsx` (`vitest` + `@testing-library/react`, `QueryClientProvider`,
`MemoryRouter`).

> `useRegions` замокан (встроенный список регионов, без сети); `getPlans`/`deletePlan`
> (`api/endpoints`) замоканы; `useNavigate` замокан, чтобы проверять переход по клику на
> строку без реального роутинга.

| Test | Scenario | Expected result |
|---|---|---|
| `prompts for a region before showing any plans` | Регион не выбран | Текст «Выберите регион, чтобы увидеть его планы.»; `getPlans` не вызван |
| `lists the region's plans once loaded` | Выбран регион, `getPlans` вернул один план (`status: 'done'`) | Виден «План №42» и статус «Готов»; `getPlans` вызван с `('east', null)` |
| `shows an empty-state message when the region has no plans` | `getPlans` вернул `[]` | Текст «У этого региона ещё нет построенных планов.» |
| `opens the plan on a row click` | Клик по строке плана | `navigate` вызван с `/plan/42` |
| `opens the delete confirmation without navigating when its button is clicked` | Клик по кнопке «Удалить» строки | Виден диалог `PlanDeleteConfirm` («Удалить план №42?»); `navigate` не вызван |
| `removes the deleted plan from the list` | Подтверждено удаление в диалоге | `deletePlan` вызван с `42`; после инвалидации списка строка плана исчезает |

## `PlanDeleteConfirm` — подтверждение удаления плана

Файл: `PlanDeleteConfirm.test.tsx` (`vitest` + `@testing-library/react`, `QueryClientProvider`).

> `deletePlan` (`api/endpoints`) замокан.

| Test | Scenario | Expected result |
|---|---|---|
| `warns that replans made from this plan are deleted with it` | Диалог открыт | Виден текст «Все перепланирования, сделанные от этого плана, тоже будут удалены.» |
| `deletes the plan and reports it to the parent` | Нажата «Удалить» | `deletePlan` вызван с `planId`, `onDeleted` вызван |
| `shows the dictionary message when the plan is already gone (404)` | `deletePlan` реджектится `ApiError(404)` | Текст «План уже удалён» |
| `shows the dictionary message when the plan is still running (409)` | `deletePlan` реджектится `ApiError(409)` | Текст «План ещё строится — подождите и попробуйте снова» |
