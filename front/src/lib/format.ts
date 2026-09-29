// All datetimes in this app are naive local time, never UTC-converted —
// these helpers only ever do string slicing, no timezone-aware Date math.

export function timeOnly(plannedArrival: string): string {
  // '2026-08-17T10:05:00' -> '10:05'. The trailing (?::\d{2})? is required:
  // without it, matching bare `\d{2}:\d{2}$` against a string that ends in
  // seconds finds "05:00" (minutes:seconds) instead of "10:05" (hours:minutes).
  const match = plannedArrival.match(/(\d{2}:\d{2})(?::\d{2})?$/);
  return match ? match[1] : plannedArrival;
}

export function formatKm(value: number): string {
  return `${value.toFixed(1).replace('.', ',')} км`;
}

export function formatMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h > 0 ? `${h} ч ` : ''}${m} мин`;
}

// Accepts 'HH:MM', 'HH:MM:SS', or a naive datetime ending in one of those
// (window_start / shift_start etc. — always local time, never UTC).
export function minutesSinceMidnight(value: string): number {
  const match = value.match(/(\d{2}):(\d{2})(?::\d{2})?$/);
  if (!match) return 0;
  return Number(match[1]) * 60 + Number(match[2]);
}

export function minutesToTimeLabel(minutes: number): string {
  const h = Math.floor(minutes / 60) % 24;
  const m = minutes % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

// '2026-08-17T09:05:00' -> '17.08.2026, 09:05'.
export function formatDateTime(value: string): string {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})/);
  if (!match) return value;
  const [, year, month, day, time] = match;
  return `${day}.${month}.${year}, ${time}`;
}

export function formatSignedDelta(value: number, unit: (v: number) => string): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${unit(Math.abs(value))}`;
}
