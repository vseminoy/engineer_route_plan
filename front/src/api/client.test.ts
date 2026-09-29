import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, NetworkError, http } from './client';
import { isFieldErrors } from '@/lib/fieldErrors';

function stubFetch(response: Response) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
}

async function catchError(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (err) {
    return err;
  }
  throw new Error('expected the promise to reject');
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('http error parsing', () => {
  it('400 with message keeps it, with no field errors', async () => {
    stubFetch(
      new Response(JSON.stringify({ message: 'Регион не найден' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' }
      })
    );

    const err = (await catchError(http.get('/regions'))) as ApiError;

    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.body && !isFieldErrors(err.body) ? err.body.message : undefined).toBe('Регион не найден');
  });

  it('400 with fields carries one entry per field', async () => {
    stubFetch(
      new Response(
        JSON.stringify({ fields: [{ name: 'region', message: 'Неизвестный код региона' }] }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      )
    );

    const err = (await catchError(http.get('/regions'))) as ApiError;

    expect(err.body && isFieldErrors(err.body) ? err.body.fields : undefined).toEqual([
      { name: 'region', message: 'Неизвестный код региона' }
    ]);
  });

  it.each([404, 501, 503])('%i has no body to parse', async (status) => {
    stubFetch(new Response(null, { status }));

    const err = (await catchError(http.get('/plan/1'))) as ApiError;

    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(status);
    expect(err.body).toBeUndefined();
  });

  it('carries the X-Request-ID header', async () => {
    stubFetch(new Response(null, { status: 500, headers: { 'X-Request-ID': 'req-42' } }));

    const err = (await catchError(http.get('/plan/1'))) as ApiError;

    expect(err.requestId).toBe('req-42');
  });

  it('a fetch that never reaches the server throws NetworkError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    const err = await catchError(http.get('/regions'));

    expect(err).toBeInstanceOf(NetworkError);
  });

  it('successful response is returned as JSON', async () => {
    stubFetch(new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }));

    await expect(http.get('/regions')).resolves.toEqual([]);
  });
});
