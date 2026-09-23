import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, http } from './client';

function stubFetch(response: Response) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
}

async function catchApiError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (err) {
    if (err instanceof ApiError) return err;
    throw err;
  }
  throw new Error('expected ApiError');
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('http error parsing', () => {
  it('501 without body → "not implemented" message', async () => {
    stubFetch(new Response(null, { status: 501, statusText: 'Not Implemented' }));

    const err = await catchApiError(http.get('/regions'));

    expect(err.status).toBe(501);
    expect(err.message).toBe('Эта функция ещё не реализована');
  });

  it('error with JSON body keeps its message', async () => {
    stubFetch(
      new Response(JSON.stringify({ error_code: 'PLAN_NOT_FOUND', message: 'План не найден' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' }
      })
    );

    const err = await catchApiError(http.get('/plan/1'));

    expect(err.errorCode).toBe('PLAN_NOT_FOUND');
    expect(err.message).toBe('План не найден');
  });

  it('other status without body falls back to statusText', async () => {
    stubFetch(new Response(null, { status: 503, statusText: 'Service Unavailable' }));

    const err = await catchApiError(http.get('/regions'));

    expect(err.status).toBe(503);
    expect(err.errorCode).toBe('UNKNOWN');
    expect(err.message).toBe('Service Unavailable');
  });

  it('successful response is returned as JSON', async () => {
    stubFetch(new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }));

    await expect(http.get('/regions')).resolves.toEqual([]);
  });
});
