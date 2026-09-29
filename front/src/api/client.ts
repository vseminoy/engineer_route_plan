import type { ValidationError } from './generated/schemas';

// The only status with a response body is 400 (ValidationError, from `common.yaml`);
// every other status carries none, so `body` is set for 400 alone.
export class ApiError extends Error {
  constructor(
    public status: number,
    public requestId: string | null,
    public body?: ValidationError
  ) {
    super(`Request failed with status ${status}`);
  }
}

// `fetch` itself failed (offline, DNS, CORS) — no server response to read a status from.
export class NetworkError extends Error {
  constructor() {
    super('Network error');
  }
}

const BASE_URL = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers:
        init?.body && !(init.body instanceof FormData)
          ? { 'Content-Type': 'application/json', ...init.headers }
          : init?.headers
    });
  } catch {
    throw new NetworkError();
  }

  if (!res.ok) {
    const requestId = res.headers.get('X-Request-ID');
    const body = res.status === 400 ? ((await res.json()) as ValidationError) : undefined;
    throw new ApiError(res.status, requestId, body);
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
