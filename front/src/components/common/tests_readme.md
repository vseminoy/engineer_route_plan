# Тесты общих компонентов (`front/src/components/common/`)

## Содержание

- [`FullScreenErrorNotice` — полноэкранное уведомление с повтором](#fullscreenerrornotice--полноэкранное-уведомление-с-повтором)

---

## `FullScreenErrorNotice` — полноэкранное уведомление с повтором

Файл: `FullScreenErrorNotice.test.tsx` (`vitest` + `@testing-library/react`).

| Test | Scenario | Expected result |
|---|---|---|
| `shows the message and calls onRetry when the button is clicked` | Клик по кнопке повтора | Текст сообщения виден, `onRetry` вызван один раз |
| `disables the button and swaps its label while retrying` | `retrying={true}` | Кнопка показывает «Строим…» и недоступна |
