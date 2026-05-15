/** API base (Vite proxy → backend in dev). */
export function apiBase(): string {
  const v = import.meta.env.VITE_API_BASE_URL;
  if (typeof v === 'string' && v.length > 0) return v.replace(/\/$/, '');
  return '';
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {}
): Promise<T> {
  const { json, headers: hdr, ...rest } = init;
  const headers = new Headers(hdr);
  if (json !== undefined) {
    headers.set('Content-Type', 'application/json');
  }
  const res = await fetch(`${apiBase()}${path}`, {
    ...rest,
    headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text) as unknown;
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    if (res.status === 401) {
      window.dispatchEvent(new CustomEvent('auth:logout'));
    }
    const err = new Error(`HTTP ${res.status}`) as Error & { status: number; body: unknown };
    err.status = res.status;
    err.body = data;
    throw err;
  }
  return data as T;
}

export async function apiUpload<T>(path: string, form: FormData, token: string | null): Promise<T> {
  const headers: HeadersInit = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${apiBase()}${path}`, { method: 'POST', headers, body: form });
  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text) as unknown;
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    if (res.status === 401) {
      window.dispatchEvent(new CustomEvent('auth:logout'));
    }
    const err = new Error(`HTTP ${res.status}`) as Error & { status: number; body: unknown };
    err.status = res.status;
    err.body = data;
    throw err;
  }
  return data as T;
}

export function formatApiError(err: unknown): string {
  if (err && typeof err === 'object' && 'body' in err) {
    const body = (err as { body?: unknown }).body;
    if (body && typeof body === 'object' && 'error' in body) {
      const e = (body as { error?: { message?: string } }).error?.message;
      if (typeof e === 'string' && e.length > 0) return e;
    }
    if (typeof body === 'string' && body.length > 0) return body;
  }
  if (err instanceof Error) return err.message;
  return 'İstek başarısız';
}
