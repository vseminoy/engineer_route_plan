# Тесты хуков TanStack Query (`front/src/queries/`)

## Содержание

- [`usePlan.ts` — интервал опроса растущего плана](#useplants--интервал-опроса-растущего-плана)
- [`usePlanCompare.ts` — сравнение с baseline](#useplancomparets--сравнение-с-baseline)
- [`useRenamePlan.ts` — обновление кэша по ответу переименования](#userenameplants--обновление-кэша-по-ответу-переименования)

---

## `usePlan.ts` — интервал опроса растущего плана

Файл: `usePlan.test.ts` (`vitest`).

> Тестируется чистая функция `planRefetchInterval`, а не сам хук: она и есть решение
> «опрашивать или остановиться», которое `usePlan` передаёт в `refetchInterval`
> TanStack Query — сама обвязка хука (`useQuery`, кэш) здесь не проверяется.

| Test | Scenario | Expected result |
|---|---|---|
| `keeps polling every 2s while the build is running` | `planRefetchInterval('running')` | `RUNNING_POLL_INTERVAL_MS` (2000) |
| `stops polling once the status is done` | `planRefetchInterval('done')` | `false` |
| `stops polling once the status is failed` | `planRefetchInterval('failed')` | `false` |
| `stops polling before the first response arrives (no data yet)` | `planRefetchInterval(undefined)` | `false` |

## `usePlanCompare.ts` — сравнение с baseline

Файл: `usePlanCompare.test.ts` (`vitest`).

> Тестируется чистая функция `planCompareReady`, а не сам хук: она и есть решение
> «звать `GET /plan/{id}/compare` или ещё нет» — backend отклоняет сравнение `400`,
> если хотя бы один из двух планов не в статусе `done`. Сам запрос и разбор ответа —
> `comparePlan` (`api/endpoints.ts`) и `mapPlanCompare` (`api/mappers.ts`, тесты в
> `api/mappers.test.ts`).

| Test | Scenario | Expected result |
|---|---|---|
| `is false while either plan is still running or failed` | `main`/`baseline` статусы — не оба `done` | `false` |
| `is false with no baseline plan selected yet` | `baselinePlanId` — `null` | `false` |
| `is true once both the main and baseline plans are done` | Оба статуса — `done` | `true` |

## `useRenamePlan.ts` — обновление кэша по ответу переименования

Файл: `useRenamePlan.test.tsx` (`vitest`, `QueryClientProvider`).

> `renamePlan` (`api/endpoints`) замокан.

| Test | Scenario | Expected result |
|---|---|---|
| `writes the renamed summary into every cached plans-list page of the region, without refetching` | Успешное переименование; `['plans', region, null]` уже закэширован списком с этим планом | Запись с этим `planId` в кэше заменена ответом мутации (новый `name`), `getPlans` не вызывается повторно |
| `merges the new name into the cached single-plan entry, without refetching` | Тот же план также закэширован под `['plan', planId]` (открыт `PlanScreen`) | Кэш `['plan', planId]` — тот же объект с обновлённым `name`, остальные поля не тронуты, `getPlan` не вызывается повторно |
| `leaves the single-plan cache untouched when that plan was never opened` | `['plan', planId]` не закэширован | Мутация не создаёт новую запись в кэше |
