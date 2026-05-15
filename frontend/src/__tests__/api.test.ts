import { describe, it, expect, vi, beforeEach } from 'vitest';
import { streamChat } from '../lib/api';

// ---------------------------------------------------------------------------
// streamChat — SSE parsing
// ---------------------------------------------------------------------------

function makeTextStream(chunks: string[]) {
  const encoder = new TextEncoder();
  let i = 0;
  const readable = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(encoder.encode(chunks[i++]));
      } else {
        controller.close();
      }
    },
  });
  return readable;
}

function makeMockResponse(status: number, body: ReadableStream | null, bodyText?: string) {
  if (body) {
    return {
      ok: status >= 200 && status < 300,
      status,
      body,
      text: async () => '',
    } as unknown as Response;
  }
  return {
    ok: status >= 200 && status < 300,
    status,
    body: null,
    text: async () => bodyText ?? '',
  } as unknown as Response;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('streamChat', () => {
  it('calls onMeta, onToken, onFinal in order', async () => {
    const sse = [
      'event: meta\ndata: {"conversation_id":"abc"}\n\n',
      'event: token\ndata: {"text":"Mer"}\n\n',
      'event: token\ndata: {"text":"haba"}\n\n',
      'event: final\ndata: {"message":"Merhaba","intent":"general","sources":[],"rag_used":false,"escalated":false,"safety_flag":false,"safety_reason":""}\n\n',
    ];

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeMockResponse(200, makeTextStream(sse))));

    const received: string[] = [];
    await streamChat(
      '/api/v1/chat/stream',
      { method: 'POST', json: { message: 'hi' } },
      {
        onMeta: (d) => received.push(`meta:${d.conversation_id}`),
        onToken: (t) => received.push(`token:${t}`),
        onFinal: (d) => received.push(`final:${d.intent}`),
      }
    );

    expect(received).toEqual(['meta:abc', 'token:Mer', 'token:haba', 'final:general']);
  });

  it('handles multi-chunk frames correctly', async () => {
    // The SSE frame arrives split across two chunks
    const sse = [
      'event: meta\ndata: {"conversation',
      '_id":"xyz"}\n\nevent: final\ndata: {"message":"ok","intent":"g","sources":[],"rag_used":false,"escalated":false,"safety_flag":false,"safety_reason":""}\n\n',
    ];

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeMockResponse(200, makeTextStream(sse))));

    const metas: string[] = [];
    await streamChat(
      '/api/v1/chat/stream',
      { method: 'POST', json: {} },
      { onMeta: (d) => metas.push(d.conversation_id) }
    );

    expect(metas).toEqual(['xyz']);
  });

  it('throws on HTTP 400', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          makeMockResponse(400, null, JSON.stringify({ error: { message: 'Bad request' } }))
        )
    );

    await expect(
      streamChat('/api/v1/chat/stream', { method: 'POST', json: {} }, {})
    ).rejects.toThrow('Bad request');
  });

  it('retries on 500 and eventually throws', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(makeMockResponse(500, null, 'Internal Server Error'));
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      streamChat('/api/v1/chat/stream', { method: 'POST', json: {} }, {})
    ).rejects.toThrow();

    // maxAttempts = 3
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('calls onError when stream emits error event', async () => {
    const sse = [
      'event: meta\ndata: {"conversation_id":"e1"}\n\n',
      'event: error\ndata: {"message":"upstream_error"}\n\n',
    ];

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeMockResponse(200, makeTextStream(sse))));

    const errors: string[] = [];
    await streamChat(
      '/api/v1/chat/stream',
      { method: 'POST', json: {} },
      { onError: (m) => errors.push(m) }
    );

    expect(errors).toContain('upstream_error');
  });
});
