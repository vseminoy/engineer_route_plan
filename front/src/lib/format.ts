// All datetimes in this app are naive local time, never UTC-converted
// (BR-21 / AGENTS.md) — these helpers only ever do string slicing, no
// timezone-aware Date math.

export function timeOnly(plannedArrival: string): string {
  // 'YYYY-MM-DD HH:MM' -> 'HH:MM'
  const match = plannedArrival.match(/(\d{2}:\d{2})$/);
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

export function formatSignedDelta(value: number, unit: (v: number) => string): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${unit(Math.abs(value))}`;
}
