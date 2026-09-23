# Полная спецификация — Frontend

Родительский документ: [`04_tor_frontend.md`](04_tor_frontend.md). API-контракт — [`05_spec_backend.md`](05_spec_backend.md#4-api-контракт).

## 1. Дерево экранов и маршрутизация

```
/                       → Экран загрузки данных (выбор региона + источник данных)
/plan/:planId           → Рабочий экран диспетчера
  ├─ карта (всегда видна)
  ├─ вкладка "Бригады и маршруты"
  ├─ вкладка "Неназначенные заявки"
  ├─ вкладка "Метрики"
  └─ вкладка "Перепланирование"
/plan/:planId/ticket/:ticketId  → модалка/страница объяснения (на мобильном — отдельный экран)
```

На мобильной раскладке (≤768px) вкладки `/plan/:planId` превращаются в нижнюю панель (bottom navigation), карта — полноэкранная по умолчанию.

## 2. Дерево компонентов (React)

```
<App>
 ├─ <DataLoadScreen>
 │   ├─ <RegionSelect>
 │   ├─ <FileUploadForm tickets? engineers? />
 │   └─ <DemoDatasetButton region />
 ├─ <PlanScreen planId>
 │   ├─ <MapView>
 │   │   ├─ <EngineerRouteLayer engineerId color polyline />   (по одному на бригаду)
 │   │   ├─ <TicketMarker ticket status priority onClick />
 │   │   └─ <EngineerStartMarker engineer />
 │   ├─ <SidePanel>            (справа на десктопе / bottom sheet на мобильном)
 │   │   ├─ <Tabs>
 │   │   │   ├─ <EngineerListTab>
 │   │   │   │   └─ <EngineerCard engineer stops totalDistance totalTime />
 │   │   │   ├─ <UnassignedListTab>
 │   │   │   │   └─ <UnassignedTicketCard ticket reasonText onClick />
 │   │   │   ├─ <MetricsTab>
 │   │   │   │   ├─ <MetricComparisonCard main baseline label />  (x2: исполнители, пробег)
 │   │   │   │   └─ <OptionalMetricsBlock loadBalance? planStability? />
 │   │   │   └─ <ReplanTab>
 │   │   │       ├─ <NewUrgentTicketForm />
 │   │   │       ├─ <CancelTicketForm ticketOptions />
 │   │   │       ├─ <EngineerUnavailableForm engineerOptions />
 │   │   │       └─ <ReplanButton />
 │   ├─ <TicketExplanationModal ticket assignment explanationText />
 │   └─ <DiffBanner diff />    (появляется после успешного /replan, с кнопкой "Показать детали")
 └─ <ErrorToast /> <LoadingOverlay />
```

## 3. Спецификация по экранам

### 3.1. `DataLoadScreen`

- Выбор региона: `east` / `south_east` / `south_center` (описание регионов — `07_data_dictionary.md`).
- Источник данных: загрузка файла (CSV/JSON, drag-n-drop + кнопка выбора) **или** кнопка «Использовать демо-набор».
- Валидация на клиенте — по спеке API (§6, «Валидация форм»): регион из `enum`, расширение `.csv`/`.json`, непустой файл, предельный размер файла. Содержимое файла проверяет backend: ответ `400` с `fields` показывается инлайн под соответствующими полями формы (`region`, `file`), `400` с `message` — под полем загрузки файла.
- После успешной загрузки → редирект на `/plan/:planId` (после вызова `POST /plan/build`).
- Состояние загрузки — `LoadingOverlay` с текстом «Строим план…» (реальный запрос может занимать несколько секунд).

### 3.2. `MapView`

- Библиотека: `react-leaflet`, тайлы OSM.
- Автоцентрирование по bounding box всех точек плана при первой загрузке.
- `TicketMarker`: цвет/форма зависят от:
  - приоритета (`urgent` — красная обводка, `normal` — стандартная);
  - статуса (`unassigned` — серый/штрих-маркер, назначенные — цвет бригады, `completed` — приглушённый).
- `EngineerRouteLayer`: полилиния по `route[].planned_arrival`-порядку, отдельный цвет на бригаду (детерминированная палитра по `engineer_id`), стрелки направления опционально.
- Клик по `TicketMarker` → открыть `TicketExplanationModal` для этой заявки.
- Клик по полилинии/маркеру бригады → подсветка соответствующей `EngineerCard` в панели (и наоборот, hover в списке подсвечивает маршрут на карте).

### 3.3. `EngineerListTab` / `EngineerCard`

Поля карточки: имя бригады, число заявок, суммарное время в пути, суммарный пробег, список остановок в порядке посещения (адрес + плановое время прибытия). Соответствует FR-09.

### 3.4. `UnassignedListTab` / `UnassignedTicketCard`

Поля: адрес, требуемый навык, окно времени, `reasonText` — человекочитаемый текст из `unassigned[].explanation` (не код `reason_code`). Клик → та же `TicketExplanationModal`, но с блоком причины вместо блока назначения.

### 3.5. `TicketExplanationModal`

- Если заявка назначена: адрес, окно времени, бригада, время прибытия, полный текст `assignment.explanation` из API.
- Если не назначена: полный текст `unassigned.explanation`, отдельно — понятный ярлык причины (маппинг `reason_code → человекочитаемый заголовок`, см. таблицу ниже).
- На мобильном — полноэкранная модалка вместо popup.

| `reason_code` | Заголовок в UI |
|---|---|
| `no_skill` | «Нет бригады с нужной квалификацией» |
| `no_time_slot` | «Ни одна бригада не успевает в это временное окно» |
| `no_vehicle` | «Нет бригады с нужным типом транспорта» |
| `shift_overflow` | «Работа не помещается в смену ни одной подходящей бригады» |
| `no_equipment` | «Не хватает оборудования у доступных бригад» |
| `all_eligible_engineers_booked_elsewhere` | «Подходящие бригады есть, но все уже заняты другими заявками в это время» |

### 3.6. `MetricsTab`

- `MetricComparisonCard` ×2 (обязательные метрики, FR-11/FR-12): «Задействовано исполнителей» (основной план vs baseline), «Суммарный пробег» (основной план vs baseline), явное дельта-значение и знак улучшения (зелёный/красный индикатор).
- `IdleTimeBlock` (обязательный, FR-23): простой по каждой бригаде (`idle_time_by_engineer_min`) — только отображение, без сравнения с baseline и без индикатора «лучше/хуже» (метрика не оптимизируется).
- `OptionalMetricsBlock` (если backend вернул поля `load_balance`, `plan_stability`): распределение загрузки по бригадам (мини-барчарт), значение `PlanStability` после последнего перепланирования.

### 3.7. `ReplanTab`

- Три формы-переключателя (radio) по типу события:
  - **Новая срочная заявка** — форма полей заявки (адрес, окно, навык фиксирован как «Авария», `duration_min` — 80 мин по умолчанию из норматива, время на объекте без дороги; полный 100-минутный норматив BR-14 = 20 мин на дорогу до ТКД (conditions.md №45) + эти 80 мин).
  - **Отмена заявки** — выбор существующей заявки из списка назначенных.
  - **Недоступность бригады** — выбор бригады из списка.
- Кнопка «Перестроить план» → `POST /plan/{planId}/replan`; во время запроса — `LoadingOverlay`.
- После ответа: обновление карты/панелей новым планом + показ `DiffBanner`.

### 3.8. `DiffBanner` / diff-вид

- Короткий баннер: «Изменено назначений: N» со ссылкой «Показать детали».
- Детали — список: заявка, было (бригада/время) → стало (бригада/время); отдельно — «новые назначения» и «сняты с плана».
- На карте изменённые маршруты временно подсвечиваются (например, пунктиром или анимацией) в течение сессии просмотра diff.

## 4. Управление состоянием и данными

- **TanStack Query**: ключи кэша `['plan', planId]`, `['tickets', regionId]`, `['engineers', regionId]`; инвалидация `['plan', planId]` после успешного `replan`/`patch status`.
- **Zustand-стор** (`useUiStore`): активная вкладка панели, выбранная заявка для модалки, состояние diff-подсветки, выбранный регион на экране загрузки. Только UI-состояние, не бизнес-данные.
- Бизнес-данные (планы, заявки, бригады, метрики) не дублируются в Zustand — единственный источник истины — кэш TanStack Query от backend.

## 5. TypeScript-типы (соответствие API-контракту backend)

Типы API, HTTP-клиент и схемы валидации форм **генерируются из спеки backend** инструментом [orval](https://orval.dev), руками не пишутся и не редактируются. Один конфиг `front/orval.config.ts`, вход — корень спеки `back/openapi/openapi.yaml` (внешние `$ref` на `common.yaml` разрешены через `input.parserOptions.externalRefs.allow`), две цели:

| Цель | Настройки | Что получается | Где лежит |
|---|---|---|---|
| Клиент и типы | `client: 'fetch'`, `schemas` | функции вызова эндпоинтов с ответами, типизированными по кодам (`400` → `ValidationError`, остальные коды ошибок — без тела); типы всех схем спеки, включая `ValidationError`/`FieldError` из `common.yaml` | `src/api/generated/` |
| Валидация форм | `client: 'zod'`, `override.zod.strict` (все места — `additionalProperties: false` спеки становится `strictObject`), `override.zod.dateTimeOptions: { local: true }` (наивное время без часового пояса, как в API) | zod-схемы тела, query- и path-параметров каждой операции со всеми ограничениями спеки; константы ограничений (`…Max`, `…RegExp`) — для атрибутов полей ввода (`maxLength`) | `src/api/generated/zod/` |

- Версия zod — 4.
- Генерация — скрипт `npm run gen:api`; сгенерированные файлы коммитятся, и CI проверяет, что повторная генерация не даёт diff (спека изменилась — клиент перегенерирован в том же коммите).
- Сгенерированный клиент встраивается в хуки TanStack Query (§4); маппинг ответа API в доменные типы UI (ниже) — в `src/api/mappers.ts`, а не в сгенерированных файлах.
- `uniqueItems` генератор не переносит: повторы значений в массиве исключаются самим элементом формы (чекбоксы/мультиселект), а backend отбивает их независимо.

Ниже — доменные типы UI, в которые маппятся ответы API:

```ts
type Skill = 'local_work' | 'connection' | 'emergency';
type VehicleType = 'car' | 'foot' | 'bike' | 'public_transport';
type Priority = 'normal' | 'urgent';
type TicketStatus = 'not_sent' | 'sent' | 'en_route' | 'in_progress' | 'completed' | 'cancelled' | 'overdue';
type UnassignedReason = 'no_skill' | 'no_time_slot' | 'no_vehicle' | 'shift_overflow' | 'no_equipment' | 'all_eligible_engineers_booked_elsewhere';

interface RouteStop {
  ticketId: number;
  sequenceNo: number;
  plannedArrival: string;       // 'YYYY-MM-DD HH:MM'
  travelTimeMin: number;
  travelDistanceKm: number;
  explanation: string;
}

interface EngineerRoute {
  engineerId: number;
  name: string;
  route: RouteStop[];
  totalDistanceKm: number;
  totalTravelTimeMin: number;
  idleTimeMin: number;          // FR-23, обязательное поле, только для отображения
}

interface UnassignedTicket {
  ticketId: number;
  reasonCode: UnassignedReason;
  explanation: string;
}

interface PlanMetrics {
  engineersUsed: number;
  totalDistanceKm: number;
  distanceByEngineer: Record<string, number>;
  assignedCount: number;
  unassignedCount: number;
  idleTimeByEngineerMin: Record<string, number>;  // FR-23, обязательное поле
  loadBalanceStdDev?: number;
  planStability?: number;
}

interface Plan {
  planId: number;
  algorithm: 'or_tools' | 'baseline_fcfs';
  parentPlanId?: number;
  engineers: EngineerRoute[];
  unassigned: UnassignedTicket[];
  metrics: PlanMetrics;
  diff?: PlanDiff;
}

interface PlanDiff {
  changedAssignments: Array<{
    ticketId: number;
    beforeEngineerId?: number;
    afterEngineerId?: number;
    beforeSequenceNo?: number;
    afterSequenceNo?: number;
  }>;
  newlyAssigned: number[];
  newlyUnassigned: number[];
  reassignedFromUnavailableEngineer: number[];
  planStability: number;
}
```

## 6. Обработка ошибок

Формат ошибок backend — [`05_spec_backend.md` §4.5](05_spec_backend.md#45-ошибки).

**Валидация форм.** Каждое поле ввода проверяется на клиенте до отправки — по тем же ограничениям, что и на backend: источник один — спека API (`back/openapi/openapi.yaml` и `common.yaml`), где у каждого входного параметра записаны `maxLength`/`minLength`, `pattern`, `format`, `enum`, `minimum`/`maximum`, `maxItems`. Схемы валидации форм (zod) генерируются из спеки orval'ом (§5), а не пишутся руками — ручная копия ограничений расходится со спекой при первой её правке; ограничения, нужные элементу ввода (`maxLength`), берутся из сгенерированных констант. Имена полей формы совпадают с именами параметров в спеке, чтобы ошибки из `fields` ответа `400` показывались у своих полей. Клиентская проверка — для удобства диспетчера, а не замена серверной: backend проверяет те же ограничения независимо.

- **`400`** — единственный ответ с телом. `fields` — ошибки показываются у соответствующих полей формы; `message` — текст показывается как есть (он уже сформулирован для диспетчера) у формы или через `ErrorToast`.
- **Остальные коды — без тела.** Текст формирует фронтенд по словарю «эндпоинт + код ответа» → UI-сообщение (аналогично таблице `reason_code`); для кода, которого нет в словаре эндпоинта, — общий текст по коду (`404` «Не найдено», `500` «Ошибка сервера», `501` «Функция ещё в разработке»). Показываются через `ErrorToast` и не блокируют весь экран, кроме `503` на построении плана/перепланировании (недоступен сервис маршрутов — полноэкранное уведомление с предложением повторить).
- **Сетевая ошибка** (ответ не получен) — общий текст «Нет связи с сервером» через `ErrorToast`.
- Для `5xx` к сообщению добавляется значение заголовка `X-Request-ID` («Код обращения: …») — по нему backend находит запрос в логах.

## 7. Доступность и адаптивность (детализация FR-31)

- Точки перелома: `≥1024px` (desktop, карта + панель side-by-side), `768–1023px` (планшет, панель уже, вкладки), `≤767px` (мобильный, панель — bottom sheet/вкладки, карта полноэкранная по умолчанию).
- Минимальный размер тач-таргета — 44×44px для кнопок событий и маркеров списка.
- Цветовая палитра маркеров/маршрутов проверяется на контраст (не полагаться только на цвет — дублировать иконкой/паттерном для приоритета и статуса).

## 8. Тестовый план фронтенда (минимум)

1. `MapView` рендерит корректное число маркеров/полилиний по фикстуре `Plan`.
2. `TicketExplanationModal` показывает разные блоки для назначенной/неназначенной заявки.
3. `ReplanTab` блокирует отправку формы без обязательных полей события.
4. `DiffBanner` корректно отображается только при наличии поля `diff` в ответе.
5. Раскладка `PlanScreen` при ширине 375px не создаёт горизонтальный скролл.
