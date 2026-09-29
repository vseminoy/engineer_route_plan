import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { fieldErrorsFromApi, fieldErrorsFromZod } from './fieldErrors';

describe('fieldErrorsFromZod', () => {
  it('names a nested array field the way the spec does', () => {
    const schema = z.object({ engineers: z.array(z.object({ skills: z.string() })) });
    const result = schema.safeParse({ engineers: [{ skills: 1 }] });

    const errors = fieldErrorsFromZod(result.error!);

    expect(Object.keys(errors)).toEqual(['engineers[0].skills']);
  });
});

describe('fieldErrorsFromApi and fieldErrorsFromZod', () => {
  it('give the same record for the same field name', () => {
    const schema = z.object({ region: z.string().min(1) });
    const zodResult = schema.safeParse({ region: '' });

    const fromZod = fieldErrorsFromZod(zodResult.error!);
    const fromApi = fieldErrorsFromApi({ fields: [{ name: 'region', message: 'Пустой регион' }] });

    expect(Object.keys(fromZod)).toEqual(Object.keys(fromApi));
  });
});
