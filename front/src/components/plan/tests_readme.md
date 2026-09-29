# Тесты экрана плана (`front/src/components/plan/`)

## Содержание

- [`PlanScreen` — переходы `running`/`done`/`failed`](#planscreen--переходы-runningdonefailed)
- [`ReplanTab` — форма события перепланирования](#replantab--форма-события-перепланирования)

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

## `ReplanTab` — форма события перепланирования

Файл: `ReplanTab.test.tsx` (`vitest` + `@testing-library/react`, `QueryClientProvider`).

> `replan` (`api/endpoints.ts`) замокан, `replanEventToRequest` — настоящий: форма строит
> тот же объект, что уйдёт на сервер, и валидирует его схемой из спеки до вызова `replan`.

| Test | Scenario | Expected result |
|---|---|---|
| `rejects an out-of-range latitude before it is sent, and does not call replan` | Событие «Новая срочная заявка», широта `999` | Ошибка схемы под полем, `replan` не вызван |
| `submits a valid event and hands the new plan id to onReplanned` | Адрес, широта и долгота заполнены корректно | `replan(42, {eventType: 'new_urgent_ticket', ...})`, `onReplanned` вызван с `plan_id` ответа |
| `shows a full-screen retry notice on a 503, and retries the same event on demand` | `replan` отклоняется `ApiError(503)`, затем клик «Повторить» | Полноэкранное уведомление «Сервис временно недоступен…», повторный клик вызывает `replan` тем же событием |
| `rejects submitting with no ticket selected, and does not call replan` | Событие «Отмена заявки», заявка не выбрана | Ошибка схемы под полем выбора заявки, `replan` не вызван |
| `submits a valid cancel event for the selected ticket` | Выбрана назначенная заявка | `replan(42, {eventType: 'ticket_cancelled', ticketId: 101})`, `onReplanned` вызван |
| `shows the conflict message when the ticket is not yet marked cancelled` | `replan` отклоняется `ApiError(409)` | Текст «Заявка ещё не отмечена отменённой — сначала измените её статус» |
| `rejects submitting with no engineer selected, and does not call replan` | Событие «Недоступность бригады», бригада не выбрана | Ошибка схемы под полем выбора бригады, `replan` не вызван |
| `submits a valid engineer_unavailable event for the selected engineer` | Выбрана бригада из `plan.engineers` | `replan(42, {eventType: 'engineer_unavailable', engineerId: 3})`, `onReplanned` вызван |
| `shows a 404 as "not found" when the engineer does not exist` | `replan` отклоняется `ApiError(404)` | Общий текст «Не найдено» (у операции нет отдельного словаря на этот код) |
