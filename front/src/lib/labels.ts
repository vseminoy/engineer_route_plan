import type { Skill, UnassignedReason } from '@/types/domain';

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

// Maps this project's flat error_code values (05_spec_backend.md §4.5) to a
// dispatcher-facing message — never the raw code or a stack trace
// (04_tor_frontend.md §6).
export const apiErrorMessage: Record<string, string> = {
  INVALID_FILE_FORMAT: 'Файл повреждён или не подходит по формату.',
  REGION_MISMATCH: 'Файл не соответствует выбранному региону.',
  PLAN_NOT_FOUND: 'План не найден — возможно, ссылка устарела.',
  OSRM_UNAVAILABLE: 'Сервис построения маршрутов недоступен. Попробуйте ещё раз.',
  VALIDATION_ERROR: 'Данные не прошли проверку.'
};

export function describeApiError(errorCode: string, fallback: string): string {
  return apiErrorMessage[errorCode] ?? fallback;
}
