import { describe, expect, it } from 'vitest';
import { MAX_UPLOAD_BYTES, validateTicketsFile } from './fileValidation';

function file(name: string, sizeBytes: number): File {
  return new File([new Uint8Array(sizeBytes)], name);
}

describe('validateTicketsFile', () => {
  it('rejects an unsupported extension', () => {
    expect(validateTicketsFile(file('tickets.txt', 10))).toBe('Поддерживаются только файлы .csv или .json.');
  });

  it('rejects an empty file', () => {
    expect(validateTicketsFile(file('tickets.csv', 0))).toBe('Файл пустой.');
  });

  it('rejects a file over the backend size limit', () => {
    expect(validateTicketsFile(file('tickets.csv', MAX_UPLOAD_BYTES + 1))).toBe('Файл слишком большой (предел — 1 МБ).');
  });

  it('accepts a non-empty .csv or .json file within the limit', () => {
    expect(validateTicketsFile(file('tickets.csv', MAX_UPLOAD_BYTES))).toBeNull();
    expect(validateTicketsFile(file('TICKETS.JSON', 10))).toBeNull();
  });
});
