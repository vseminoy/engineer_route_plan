// Checks the zod schema of POST /data/upload's multipart body doesn't express
// (it only knows `tickets_file` is a Blob): extension, non-empty, and the request
// size limit from that operation's description. A convenience for the dispatcher,
// not a security boundary — a bigger file sent around the form is rejected by the
// backend with 413.
export const MAX_UPLOAD_BYTES = 1_048_576;

export function validateTicketsFile(file: File): string | null {
  if (!/\.(csv|json)$/i.test(file.name)) return 'Поддерживаются только файлы .csv или .json.';
  if (file.size === 0) return 'Файл пустой.';
  if (file.size > MAX_UPLOAD_BYTES) return 'Файл слишком большой (предел — 1 МБ).';
  return null;
}
