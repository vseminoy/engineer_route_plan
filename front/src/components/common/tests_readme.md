# Тесты общих компонентов (`front/src/components/common/`)

## Содержание

- [`FullScreenErrorNotice` — полноэкранное уведомление с повтором](#fullscreenerrornotice--полноэкранное-уведомление-с-повтором)
- [`AppNav` — ссылки и активный раздел](#appnav--ссылки-и-активный-раздел)

---

## `AppNav` — ссылки и активный раздел

Файл: `AppNav.test.tsx` (`vitest` + `@testing-library/react`, `MemoryRouter`).

| Test | Scenario | Expected result |
|---|---|---|
| `links to the new-plan and plans-list routes` | Рендер на `/` | Ссылка «Новый план» ведёт на `/`, «Сгенерированные планы» — на `/plans` |
| `marks only the current route active` | Рендер на `/plans` | У ссылки «Сгенерированные планы» класс `app-nav__link--active`, у «Новый план» — нет |

## `FullScreenErrorNotice` — полноэкранное уведомление с повтором

Файл: `FullScreenErrorNotice.test.tsx` (`vitest` + `@testing-library/react`).

| Test | Scenario | Expected result |
|---|---|---|
| `shows the message and calls onRetry when the button is clicked` | Клик по кнопке повтора | Текст сообщения виден, `onRetry` вызван один раз |
| `disables the button and swaps its label while retrying` | `retrying={true}` | Кнопка показывает «Строим…» и недоступна |
