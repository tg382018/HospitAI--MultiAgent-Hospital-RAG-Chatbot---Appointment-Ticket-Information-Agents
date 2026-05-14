import { FormEvent, useCallback, useEffect, useState } from 'react';

import { streamChat } from './lib/api';

type ChatMsg = { role: 'user' | 'assistant'; content: string };

const SS_CONV = 'hospitai-chat-conversation-id';

function formatErr(e: unknown): string {
  if (e && typeof e === 'object' && 'body' in e) {
    const b = (e as { body: unknown }).body;
    if (b && typeof b === 'object' && 'error' in b) {
      const er = (b as { error?: { message?: string; code?: string } }).error;
      if (er?.message) return er.message;
      if (er?.code) return er.code;
    }
  }
  if (e instanceof Error) return e.message;
  return 'İstek başarısız';
}

export function ChatApp() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [draft, setDraft] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [chatErr, setChatErr] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const cid = sessionStorage.getItem(SS_CONV);
    if (cid) setConversationId(cid);
  }, []);

  const onSend = useCallback(
    async (ev: FormEvent) => {
      ev.preventDefault();
      const text = draft.trim();
      if (!text) return;
      setChatErr('');
      setSending(true);
      setDraft('');
      setMessages((m) => [
        ...m,
        { role: 'user', content: text },
        { role: 'assistant', content: '' },
      ]);
      let acc = '';
      try {
        const body: Record<string, unknown> = { message: text };
        if (conversationId) body.conversation_id = conversationId;
        await streamChat(
          '/api/v1/chat/stream',
          {
            method: 'POST',
            headers: {},
            json: body,
          },
          {
            onMeta: (d) => {
              setConversationId(d.conversation_id);
              sessionStorage.setItem(SS_CONV, d.conversation_id);
            },
            onToken: (t) => {
              acc += t;
              setMessages((m) => {
                const next = [...m];
                const last = next.length - 1;
                if (last >= 0 && next[last].role === 'assistant') {
                  next[last] = { role: 'assistant', content: acc };
                }
                return next;
              });
            },
            onFinal: (d) => {
              let msg = d.message;
              if (d.escalated) msg = `⚠️ Acil yönlendirme\n\n${msg}`;
              else if (d.safety_flag) msg = `⚠️ Güvenlik uyarısı\n\n${msg}`;
              setMessages((m) => {
                const next = [...m];
                const last = next.length - 1;
                if (last >= 0 && next[last].role === 'assistant') {
                  next[last] = { role: 'assistant', content: msg };
                }
                return next;
              });
            },
            onError: (m) => {
              throw new Error(m);
            },
          }
        );
      } catch (e) {
        setChatErr(formatErr(e));
        setDraft(text);
        setMessages((m) => {
          if (m.length < 2) return m;
          const a = m[m.length - 1];
          const u = m[m.length - 2];
          if (u.role === 'user' && u.content === text && a.role === 'assistant')
            return m.slice(0, -2);
          return m;
        });
      } finally {
        setSending(false);
      }
    },
    [conversationId, draft]
  );

  return (
    <div className="flex min-h-[70vh] flex-col">
      <header className="mb-4 border-b border-slate-800 pb-3">
        <h2 className="text-lg font-medium text-slate-100">XYZ Hospital — Sohbet</h2>
        <p className="mt-1 text-xs text-slate-500">
          Randevu ve talepler için mesajınızda ad, soyad ve gerekiyorsa TC bilgisini yazabilirsiniz.
        </p>
      </header>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto rounded-lg border border-slate-800 bg-slate-900/50 p-4">
        {messages.length === 0 ? (
          <p className="text-center text-sm text-slate-500">
            Merhaba deyin veya randevu / şikayet hakkında soru sorun.
          </p>
        ) : (
          messages.map((msg, i) => (
            <div
              key={`${i}-${msg.role}`}
              className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'ml-auto bg-emerald-900/40 text-emerald-50'
                  : 'mr-auto border border-slate-700 bg-slate-800/80 text-slate-100'
              }`}
            >
              {msg.content}
            </div>
          ))
        )}
      </div>
      {chatErr ? <p className="text-sm text-rose-400">{chatErr}</p> : null}
      <form className="mt-4 flex gap-2" onSubmit={onSend}>
        <input
          className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none ring-emerald-500/30 focus:ring-2"
          placeholder="Mesajınız…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={sending}
        />
        <button
          type="submit"
          disabled={sending || !draft.trim()}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
        >
          Gönder
        </button>
      </form>
    </div>
  );
}
