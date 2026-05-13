import { FormEvent, useCallback, useState } from 'react';

import { apiFetch } from './lib/api';
import { useAuthStore } from './store/auth';

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

type ChatResponse = {
  conversation_id: string;
  message: string;
  intent: string;
  sources: string[];
  safety_flag: boolean;
  safety_reason: string;
};

type ChatMsg = { role: 'user' | 'assistant'; content: string };

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
  const tenantSlug = useAuthStore((s) => s.tenantSlug);
  const setTenantSlug = useAuthStore((s) => s.setTenantSlug);
  const accessToken = useAuthStore((s) => s.accessToken);
  const setTokens = useAuthStore((s) => s.setTokens);
  const clear = useAuthStore((s) => s.clear);

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [authErr, setAuthErr] = useState('');

  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [draft, setDraft] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [chatErr, setChatErr] = useState('');
  const [sending, setSending] = useState(false);

  const onAuth = useCallback(
    async (ev: FormEvent) => {
      ev.preventDefault();
      setAuthErr('');
      try {
        const path = mode === 'register' ? '/api/v1/auth/register' : '/api/v1/auth/login';
        const body =
          mode === 'register'
            ? { tenant_slug: tenantSlug, email, password, full_name: fullName || null }
            : { tenant_slug: tenantSlug, email, password };
        const res = await apiFetch<TokenResponse>(path, {
          method: 'POST',
          json: body,
        });
        setTokens({ accessToken: res.access_token, refreshToken: res.refresh_token });
        setMessages([]);
        setConversationId(null);
      } catch (e) {
        setAuthErr(formatErr(e));
      }
    },
    [email, fullName, mode, password, setTokens, tenantSlug]
  );

  const onSend = useCallback(
    async (ev: FormEvent) => {
      ev.preventDefault();
      const text = draft.trim();
      if (!text || !accessToken) return;
      setChatErr('');
      setSending(true);
      setDraft('');
      setMessages((m) => [...m, { role: 'user', content: text }]);
      try {
        const body: { message: string; conversation_id?: string } = { message: text };
        if (conversationId) body.conversation_id = conversationId;
        const res = await apiFetch<ChatResponse>('/api/v1/chat', {
          method: 'POST',
          headers: { Authorization: `Bearer ${accessToken}` },
          json: body,
        });
        setConversationId(res.conversation_id);
        setMessages((m) => [...m, { role: 'assistant', content: res.message }]);
      } catch (e) {
        setChatErr(formatErr(e));
        setDraft(text);
      } finally {
        setSending(false);
      }
    },
    [accessToken, conversationId, draft]
  );

  if (!accessToken) {
    return (
      <div className="mx-auto max-w-md rounded-xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-medium text-slate-100">Giriş</h2>
        <p className="mb-4 text-sm text-slate-400">
          Varsayılan hastane: <code className="text-emerald-400">demo-hospital</code> (ilk{' '}
          <code className="text-slate-500">alembic upgrade head</code> ile oluşur).
        </p>
        <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-500">
          Tenant slug
        </label>
        <input
          className="mb-4 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none ring-emerald-500/30 focus:ring-2"
          value={tenantSlug}
          onChange={(e) => setTenantSlug(e.target.value)}
        />
        <div className="mb-4 flex gap-2">
          <button
            type="button"
            className={`rounded-lg px-3 py-1.5 text-sm ${mode === 'login' ? 'bg-emerald-600 text-white' : 'text-slate-400'}`}
            onClick={() => setMode('login')}
          >
            Giriş yap
          </button>
          <button
            type="button"
            className={`rounded-lg px-3 py-1.5 text-sm ${mode === 'register' ? 'bg-emerald-600 text-white' : 'text-slate-400'}`}
            onClick={() => setMode('register')}
          >
            Kayıt ol
          </button>
        </div>
        <form className="flex flex-col gap-3" onSubmit={onAuth}>
          {mode === 'register' ? (
            <input
              required
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none ring-emerald-500/30 focus:ring-2"
              placeholder="Ad soyad"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          ) : null}
          <input
            required
            type="email"
            autoComplete="email"
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none ring-emerald-500/30 focus:ring-2"
            placeholder="E-posta"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            required
            type="password"
            autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
            minLength={8}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none ring-emerald-500/30 focus:ring-2"
            placeholder="Şifre (min 8)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {authErr ? <p className="text-sm text-rose-400">{authErr}</p> : null}
          <button
            type="submit"
            className="rounded-lg bg-emerald-600 py-2 text-sm font-medium text-white hover:bg-emerald-500"
          >
            {mode === 'register' ? 'Kayıt ol' : 'Giriş yap'}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="flex min-h-[70vh] flex-col">
      <header className="mb-4 flex items-center justify-between border-b border-slate-800 pb-3">
        <div>
          <h2 className="text-lg font-medium text-slate-100">Sohbet</h2>
          <p className="text-xs text-slate-500">
            Tenant: {tenantSlug}
            {conversationId ? ` · Oturum: ${conversationId.slice(0, 8)}…` : ''}
          </p>
        </div>
        <button
          type="button"
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          onClick={() => {
            clear();
            setMessages([]);
            setConversationId(null);
          }}
        >
          Çıkış
        </button>
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
