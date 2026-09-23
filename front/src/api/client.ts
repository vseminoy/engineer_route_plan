import type { ApiErrorBody } from './types';

// Flat error body — { error_code, message } — per AGENTS.md's project-specific
// deviation from the profile's nested {error:{code,message}} contract.
export class ApiError extends Error {
  errorCode: string;

  constructor(body: ApiErrorBody, public status: number) {
    super(body.message);
    this.errorCode = body.error_code;
  }
}

const BASE_URL = '/api/v1';

async function parseErrorBody(res: Response): Promise<ApiErrorBody> {
  try {
    const body = (await res.json()) as ApiErrorBody;
    if (body && typeof body.error_code === 'string') return body;
  } catch {
    // fall through to the generic body below
  }
  const message =
    res.status === 501 ? 'Эта функция ещё не реализована' : res.statusText || 'Request failed';
  return { error_code: 'UNKNOWN', message };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers:
      init?.body && !(init.body instanceof FormData)
        ? { 'Content-Type': 'application/json', ...init.headers }
        : init?.headers
  });
  if (!res.ok) {
    throw new ApiError(await parseErrorBody(res), res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body !== undefined ? JSON.stringify(body) : undefined })
};
