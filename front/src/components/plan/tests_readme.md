# Тесты экрана плана (`front/src/components/plan/`)

## Содержание

- [`PlanScreen` — переходы `running`/`done`/`failed`](#planscreen--переходы-runningdonefailed)
- [`ReplanTab` — форма события перепланирования](#replantab--форма-события-перепланирования)
- [`MetricsTab` — карточка сравнения `unassignedCount`](#metricstab--карточка-сравнения-unassignedcount)
- [`IdleTimeBlock` — таблица по бригадам (справочно, без сравнения)](#idletimeblock--таблица-по-бригадам-справочно-без-сравнения)

---

## `PlanScreen` — переходы `running`/`done`/`failed`

Файл: `PlanScreen.test.tsx` (`vitest` + `@testing-library/react`, `MemoryRouter`).

> `usePlan`, `useEngineers`, `useEngineerSets`, `useTickets`, `buildPlan` и `MapView`
> замоканы: маршрутизация статуса (running/done/failed) — то, что решает сам `PlanScreen`,
> а не сеть, кэш TanStack Query или Leaflet.

| Test | Scenario | Expected result |
|---|---|---|
| `shows the waiting message while the build is still running (polling handled by usePlan itself)` | `usePlan` возвращает `{status: 'running'}` | Текст «Подождите, идёт расчёт…», карта не отрисована |
| `renders the plan once the build is done, with its name in the header instead of the static title` | `usePlan` возвращает `{status: 'done', name: 'Утренний обход', engineers: [], unassigned: [], metrics: {...}}` | Карта отрисована, заголовок содержит «Утренний обход» (не «Диспетчер»), сообщение ожидания не показано |
| `shows the failure reason and a rebuild button when the build failed, and rebuilds on click` | `usePlan` возвращает `{status: 'failed', failedReason: 'osrm_unavailable', engineerSetId: 7}`, клик «Построить заново» | Текст «Сервис маршрутов недоступен: возможно, он ещё загружает карту дорог после запуска стенда. Подождите немного и попробуйте построить план ещё раз.», `buildPlan` вызван с тем же `engineerSetId`, переход на `/plan/{новый plan_id}` |

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

## `MetricsTab` — карточка сравнения `unassignedCount`

Файл: `MetricsTab.test.tsx` (`vitest` + `@testing-library/react`).

> `usePlanCompare` замокан целиком (`vi.mock`) — компонент только рендерит то, что вернул
> хук, TanStack Query и `usePlan`/`useUiStore` за ним не участвуют.

| Test | Scenario | Expected result |
|---|---|---|
| `renders a third card for unassignedCount, alongside the two mandatory metrics` | `usePlanCompare` вернул `data` с `unassignedCount: {main: 2, baseline: 6, delta: -4}`, `plan.metrics` — `assignedCount: 43, unassignedCount: 2`, `engineerSetName="13 бригад"` | Строка «Заявок в плане: 45» идёт сразу под «Сравнение в пределах набора «13 бригад»» (из `plan.metrics`, не из `compare`), а не внутри карточки «Неназначено заявок»; карточка — `main=2`, `baseline: 6` |
| `marks a higher unassigned count than the baseline as a regression, not an improvement` | `unassignedCount: {main: 6, baseline: 2, delta: 4}` | У карточки «Неназначено заявок» класс `metric-delta--bad`, не `metric-delta--good` |

## `IdleTimeBlock` — таблица по бригадам (справочно, без сравнения)

Файл: `IdleTimeBlock.test.tsx` (`vitest` + `@testing-library/react`).

> Чистый компонент без моков: рендерит то, что передано в `engineers`/`roster`. Без заголовка
> раздела — безрамочная `<table>` с одной строкой на бригаду. Колонки «Бригада»/«Транспорт»/
> «Навыки» без видимых подписей (только `aria-label` для скринридеров), остальные — «Смена»,
> «Заявки», «Пробег», «Простой» — подписаны. Незанятые бригады идут в конце списка и серые
> (`brigade-table__row--idle`), независимо от порядка во входном `engineers`.

| Test | Scenario | Expected result |
|---|---|---|
| `renders a borderless table with one row per brigade, used and unused alike, with no label for the name/vehicle/skills columns` | Бригада с `route` из 2 остановок (`totalDistanceKm: 12.5`, `idleTimeMin: 35`) и бригада с пустым `route` (`idleTimeMin: 480`) | Видимых подписей «Бригада»/«Транспорт»/«Навыки» нет; «Смена»/«Заявки»/«Пробег»/«Простой» присутствуют; строка первой бригады содержит «2», «12,5 км», «35 мин»; строка второй — «0,0 км», «480 мин» |
| `sinks unused brigades to the bottom of the list and greys them out, regardless of input order` | `engineers={[unused, used]}` (незанятая бригада первой на входе) | Строки отрендерены в порядке «Бригада 1» (занята), затем «Бригада 2» (не занята); только вторая строка имеет класс `brigade-table__row--idle` |
