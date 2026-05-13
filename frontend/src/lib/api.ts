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
    const err = new Error(`HTTP ${res.status}`) as Error & { status: number; body: unknown };
    err.status = res.status;
    err.body = data;
    throw err;
  }
  return data as T;
}

export type StreamChatFinal = {
  conversation_id?: string;
  message: string;
  intent: string;
  sources: string[];
  rag_used: boolean;
  escalated: boolean;
  safety_flag: boolean;
  safety_reason: string;
  response?: string;
};

/** POST `/api/v1/chat/stream` — consumes Server-Sent Events (retries on transient network / 5xx). */
export async function streamChat(
  path: string,
  init: RequestInit & { json?: unknown },
  handlers: {
    onMeta?: (data: { conversation_id: string }) => void;
    onToken?: (text: string) => void;
    onFinal?: (data: StreamChatFinal) => void;
    onError?: (message: string) => void;
  }
): Promise<void> {
  const { json, headers: hdr, ...rest } = init;
  const maxAttempts = 3;
  let lastErr: Error | null = null;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const headers = new Headers(hdr);
    headers.set('Accept', 'text/event-stream');
    if (json !== undefined) {
      headers.set('Content-Type', 'application/json');
    }
    try {
      const res = await fetch(`${apiBase()}${path}`, {
        ...rest,
        method: 'POST',
        headers,
        body: json !== undefined ? JSON.stringify(json) : rest.body,
      });
      if (!res.ok || !res.body) {
        const text = await res.text();
        let msg = `HTTP ${res.status}`;
        try {
          const j = JSON.parse(text) as { error?: { message?: string } };
          if (j?.error?.message) msg = j.error.message;
        } catch {
          if (text) msg = text;
        }
        const retryable = res.status >= 500 || res.status === 429;
        lastErr = new Error(msg);
        if (retryable && attempt < maxAttempts) {
          await new Promise((r) => setTimeout(r, 350 * attempt));
          continue;
        }
        throw lastErr;
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx: number;
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          let ev = '';
          let dataLine = '';
          for (const line of frame.split('\n')) {
            if (line.startsWith('event:')) ev = line.slice(6).trim();
            else if (line.startsWith('data:')) dataLine = line.slice(5).trim();
          }
          if (!dataLine) continue;
          const data = JSON.parse(dataLine) as Record<string, unknown>;
          if (ev === 'meta') handlers.onMeta?.(data as { conversation_id: string });
          else if (ev === 'token' && typeof data.text === 'string') handlers.onToken?.(data.text);
          else if (ev === 'final') handlers.onFinal?.(data as StreamChatFinal);
          else if (ev === 'error') {
            const m = typeof data.message === 'string' ? data.message : 'stream_error';
            handlers.onError?.(m);
          }
        }
      }
      return;
    } catch (e) {
      lastErr = e instanceof Error ? e : new Error(String(e));
      if (attempt < maxAttempts) {
        await new Promise((r) => setTimeout(r, 400 * attempt));
        continue;
      }
      throw lastErr;
    }
  }
  throw lastErr ?? new Error('stream_failed');
}
