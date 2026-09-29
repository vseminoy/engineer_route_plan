import type { InvalidRowReason, PlanFailedReason, Skill, TicketStatus, UnassignedReason } from '@/types/domain';
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

// reason_code → human-readable heading, shown in the ticket explanation.
export const unassignedReasonHeading: Record<UnassignedReason, string> = {
  no_skill: 'Нет бригады с нужной квалификацией',
  no_time_slot: 'Ни одна бригада не успевает в это временное окно',
  no_vehicle: 'Нет бригады с нужным типом транспорта',
  shift_overflow: 'Работа не помещается в смену ни одной подходящей бригады',
  all_eligible_engineers_booked_elsewhere:
    'Подходящие бригады есть, но все уже заняты другими заявками в это время'
};

export const ticketStatusLabel: Record<TicketStatus, string> = {
  not_sent: 'Не отправлена',
  sent: 'Отправлена бригаде',
  en_route: 'Бригада в пути',
  in_progress: 'Работа начата',
  completed: 'Завершена',
  cancelled: 'Отменена',
  overdue: 'Просрочена'
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

// A queued build that never finished (GET /plan/{id} status: 'failed').
export const planFailedReasonText: Record<PlanFailedReason, string> = {
  osrm_unavailable: 'Сервис маршрутов недоступен',
  db_unavailable: 'База данных недоступна',
  build_error: 'Не удалось построить план',
  timeout: 'Расчёт не уложился в отведённое время',
  shutdown: 'Сервер был перезапущен во время расчёта'
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
  'POST /data/upload 413': 'Файл слишком большой (предел — 1 МБ).',
  'PATCH /tickets/{id}/status 404': 'Заявка не найдена',
  'GET /plan/{id} 404': 'План не найден — возможно, ссылка устарела',
  'POST /plan/{id}/replan 409': 'Заявка ещё не отмечена отменённой — сначала измените её статус',
  'POST /engineer-sets 409': 'Набор с таким названием уже есть в регионе',
  'DELETE /engineer-sets/{id} 404': 'Набор уже удалён',
  'DELETE /engineer-sets/{id} 409': 'Набор по умолчанию удалить нельзя'
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
