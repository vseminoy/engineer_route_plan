import type { InvalidRowReason, Skill, UnassignedReason } from '@/types/domain';
import { ApiError, NetworkError } from '@/api/client';
import { isFieldErrors } from '@/lib/fieldErrors';

export function skillLabel(skill: Skill): string {
  switch (skill) {
    case 'emergency':
      return 'Авария';
    case 'connection':
      return 'Подключение';
    case 'local_work':
      return 'Локальные работы';
  }
}

// 06_spec_frontend.md §3.5 — reason_code → human-readable heading.
export const unassignedReasonHeading: Record<UnassignedReason, string> = {
  no_skill: 'Нет бригады с нужной квалификацией',
  no_time_slot: 'Ни одна бригада не успевает в это временное окно',
  no_vehicle: 'Нет бригады с нужным типом транспорта',
  shift_overflow: 'Работа не помещается в смену ни одной подходящей бригады',
  no_equipment: 'Не хватает оборудования у доступных бригад',
  all_eligible_engineers_booked_elsewhere:
    'Подходящие бригады есть, но все уже заняты другими заявками в это время'
};

// Why a row of the uploaded file (or the demo dataset) was not loaded as a
// ticket, shown next to its row number and column.
export const invalidRowReasonText: Record<InvalidRowReason, string> = {
  missing_field: 'Нет обязательного поля',
  field_too_long: 'Значение длиннее предела',
  bad_datetime: 'Время не в формате ДД.ММ.ГГГГ Ч:ММ',
  window_order: 'Начало окна не раньше окончания',
  unknown_type: 'Тип заявки не из таблицы соответствия',
  unknown_status: 'Статус BK не из таблицы соответствия',
  address_not_found: 'Для адреса не нашлось координат'
};

// A response status with no body: text by status, used when the endpoint has
// no more specific entry below.
const statusMessage: Record<number, string> = {
  404: 'Не найдено',
  500: 'Ошибка сервера',
  501: 'Функция ещё в разработке',
  503: 'Сервис временно недоступен, попробуйте ещё раз'
};

// `"METHOD /path" (as named in the spec) + status` → a message specific to that
// operation's failure, for a status the generic table above doesn't fit well.
const endpointStatusMessage: Record<string, string> = {
  'POST /data/upload 413': 'Файл слишком большой (предел — 1 МБ).'
};

function textForStatus(endpoint: string, status: number): string {
  return endpointStatusMessage[`${endpoint} ${status}`] ?? statusMessage[status] ?? 'Ошибка сервера';
}

// The one message to show for any request error, wherever it came from: a
// network failure, a bodyless status code, or a 400 whose `message` is already
// phrased for the dispatcher. A 400 with `fields` has no single message — it
// belongs at the form's fields, not here.
export function describeError(error: unknown, endpoint: string): string {
  if (error instanceof NetworkError) return 'Нет связи с сервером';
  if (!(error instanceof ApiError)) return 'Ошибка сервера';
  if (error.status === 400 && error.body && !isFieldErrors(error.body)) {
    return error.body.message;
  }
  const text = textForStatus(endpoint, error.status);
  return error.status >= 500 && error.requestId ? `${text} Код обращения: ${error.requestId}` : text;
}
