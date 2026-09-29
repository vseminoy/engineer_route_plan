# Тесты управления статусом заявки (`front/src/components/ticket/`)

## Содержание

- [`TicketStatusControl` — выбор допустимого следующего статуса](#ticketstatuscontrol--выбор-допустимого-следующего-статуса)

---

## `TicketStatusControl` — выбор допустимого следующего статуса

Файл: `TicketStatusControl.test.tsx` (`vitest` + `@testing-library/react`).

| Test | Scenario | Expected result |
|---|---|---|
| `offers only the statuses reachable from the current one, current excluded` | `status="en_route"` | Список опций селекта — только те, что даёт `allowedNextStatuses('en_route')` |
| `calls onChange with the selected status when saved` | Выбран `en_route`, нажата «Сохранить» | `onChange` вызван с `'en_route'` |
| `shows no control for a closed status` | `status="completed"` | Текст «Статус закрыт, изменить нельзя.», селекта нет |
| `shows the error message passed by the parent` | Передан `error="Недопустимый переход"` | Текст ошибки виден под контролом |
| `disables the save button while a change is pending` | `pending={true}` | Кнопка «Сохраняем…» недоступна |
