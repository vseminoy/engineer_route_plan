# Тесты хуков TanStack Query (`front/src/queries/`)

## Содержание

- [`usePlan.ts` — интервал опроса растущего плана](#useplants--интервал-опроса-растущего-плана)
- [`usePlanCompare.ts` — сравнение с baseline](#useplancomparets--сравнение-с-baseline)

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

> Тестируется чистая функция `comparePlanMetrics`, а не сам хук — она и есть решение
> «есть с чем сравнивать или ещё нет», `usePlanCompare` только достаёт `metrics` из кэша
> обоих планов и передаёт их сюда.

| Test | Scenario | Expected result |
|---|---|---|
| `is undefined while either plan has no metrics yet (still running or failed)` | `main`/`baseline` метрики — то `undefined`, то заданы | `undefined` |
| `computes the delta (main - baseline) for both mandatory metrics once both are done` | Обе метрики заданы (`9`/`187.3` и `13`/`244.9`) | `{main, baseline, delta}` для `engineersUsed` и `totalDistanceKm` |
