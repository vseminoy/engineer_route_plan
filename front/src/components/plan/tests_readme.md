# Тесты экрана плана (`front/src/components/plan/`)

## Содержание

- [`PlanScreen` — переходы `running`/`done`/`failed`](#planscreen--переходы-runningdonefailed)

---

## `PlanScreen` — переходы `running`/`done`/`failed`

Файл: `PlanScreen.test.tsx` (`vitest` + `@testing-library/react`, `MemoryRouter`).

> `usePlan`, `useEngineers`, `useTickets`, `buildPlan` и `MapView` замоканы: маршрутизация
> статуса (running/done/failed) — то, что решает сам `PlanScreen`, а не сеть, кэш
> TanStack Query или Leaflet.

| Test | Scenario | Expected result |
|---|---|---|
| `shows the waiting message while the build is still running (polling handled by usePlan itself)` | `usePlan` возвращает `{status: 'running'}` | Текст «Подождите, идёт расчёт…», карта не отрисована |
| `renders the plan once the build is done` | `usePlan` возвращает `{status: 'done', engineers: [], unassigned: [], metrics: {...}}` | Карта отрисована, заголовок «Диспетчер», сообщение ожидания не показано |
| `shows the failure reason and a rebuild button when the build failed, and rebuilds on click` | `usePlan` возвращает `{status: 'failed', failedReason: 'osrm_unavailable'}`, клик «Построить заново» | Текст «Сервис маршрутов недоступен», `buildPlan` вызван, переход на `/plan/{новый plan_id}` |
