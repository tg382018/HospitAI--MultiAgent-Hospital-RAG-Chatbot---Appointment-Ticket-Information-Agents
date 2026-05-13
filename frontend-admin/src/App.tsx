import { useCallback, useEffect, useState } from 'react';

import { apiFetch, formatApiError } from '@/lib/api';
import {
  authHeaders,
  canManageConnector,
  canManageDocuments,
  fetchMe,
  useAuth,
  type Me,
  type UserRole,
} from '@/store/auth';

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

type DocumentRow = {
  id: string;
  title: string;
  source_type: string;
  status: string;
  chunk_count: number;
  created_at: string;
};

type DocumentListResponse = { documents: DocumentRow[] };

type TenantConnector = {
  external_hospital_base_url: string | null;
  has_external_hospital_api_key: boolean;
};

function RoleBanner({ role }: { role: UserRole | undefined }) {
  if (!role) return null;
  const docOk = canManageDocuments(role);
  const connOk = canManageConnector(role);
  if (docOk && connOk) return null;
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <p className="font-medium">Kısıtlı yetki</p>
      <p className="mt-1 text-amber-900/90">
        {!docOk && (
          <>
            Doküman yükleme ve silme yalnızca <strong>admin</strong> veya <strong>staff</strong>{' '}
            rolleriyle yapılabilir.
          </>
        )}
        {!docOk && !connOk && ' '}
        {!connOk && (
          <>
            Dış hastane bağlantısı (connector) yalnızca <strong>admin</strong> rolüyle
            düzenlenebilir.
          </>
        )}
      </p>
    </div>
  );
}

function LoginForm({ onSuccess }: { onSuccess: (access: string, me: Me) => void }) {
  const [tenantSlug, setTenantSlug] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      const tokens = await apiFetch<TokenResponse>('/api/v1/auth/login', {
        method: 'POST',
        json: { tenant_slug: tenantSlug.trim(), email: email.trim(), password },
      });
      const me = await fetchMe(tokens.access_token);
      onSuccess(tokens.access_token, me);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mx-auto max-w-md space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <h1 className="text-xl font-semibold text-slate-900">HospitAI Admin</h1>
      <p className="text-sm text-slate-600">Tenant slug ve hesabınızla giriş yapın.</p>
      {err && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {err}
        </div>
      )}
      <label className="block text-sm font-medium text-slate-700">
        Tenant slug
        <input
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          value={tenantSlug}
          onChange={(e) => setTenantSlug(e.target.value)}
          autoComplete="organization"
          required
        />
      </label>
      <label className="block text-sm font-medium text-slate-700">
        E-posta
        <input
          type="email"
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          required
        />
      </label>
      <label className="block text-sm font-medium text-slate-700">
        Şifre
        <input
          type="password"
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
          minLength={8}
        />
      </label>
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
      >
        {loading ? 'Giriş…' : 'Giriş'}
      </button>
    </form>
  );
}

export default function App() {
  const accessToken = useAuth((s) => s.accessToken);
  const me = useAuth((s) => s.me);
  const setSession = useAuth((s) => s.setSession);
  const clear = useAuth((s) => s.clear);

  const [docs, setDocs] = useState<DocumentRow[]>([]);
  const [docsErr, setDocsErr] = useState<string | null>(null);
  const [ingestTitle, setIngestTitle] = useState('');
  const [ingestContent, setIngestContent] = useState('');
  const [ingestSource, setIngestSource] = useState('manual');
  const [ingestMsg, setIngestMsg] = useState<string | null>(null);
  const [connector, setConnector] = useState<TenantConnector | null>(null);
  const [connBase, setConnBase] = useState('');
  const [connKey, setConnKey] = useState('');
  const [connMsg, setConnMsg] = useState<string | null>(null);

  const token = accessToken;
  const role = me?.role;

  const loadDocs = useCallback(async () => {
    if (!token) return;
    setDocsErr(null);
    try {
      const res = await apiFetch<DocumentListResponse>('/api/v1/documents', {
        headers: authHeaders(token),
      });
      setDocs(res.documents);
    } catch (e) {
      setDocsErr(formatApiError(e));
    }
  }, [token]);

  const loadConnector = useCallback(async () => {
    if (!token || !canManageConnector(role)) return;
    setConnMsg(null);
    try {
      const c = await apiFetch<TenantConnector>('/api/v1/admin/tenant-connector', {
        headers: authHeaders(token),
      });
      setConnector(c);
      setConnBase(c.external_hospital_base_url ?? '');
    } catch (e) {
      setConnMsg(formatApiError(e));
    }
  }, [token, role]);

  useEffect(() => {
    if (token) void loadDocs();
  }, [token, loadDocs]);

  useEffect(() => {
    if (token && canManageConnector(role)) void loadConnector();
  }, [token, role, loadConnector]);

  async function onLogout() {
    clear();
    setDocs([]);
    setConnector(null);
    setConnBase('');
    setConnKey('');
  }

  async function onIngest(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !canManageDocuments(role)) return;
    setIngestMsg(null);
    try {
      await apiFetch('/api/v1/documents/ingest-text', {
        method: 'POST',
        headers: authHeaders(token),
        json: {
          title: ingestTitle.trim(),
          content: ingestContent,
          source_type: ingestSource.trim() || 'manual',
        },
      });
      setIngestTitle('');
      setIngestContent('');
      setIngestMsg('Doküman kuyruğa alındı.');
      await loadDocs();
    } catch (err) {
      setIngestMsg(formatApiError(err));
    }
  }

  async function onDelete(id: string) {
    if (!token || !canManageDocuments(role)) return;
    if (!window.confirm('Bu dokümanı ve vektörlerini silmek istiyor musunuz?')) return;
    try {
      await apiFetch(`/api/v1/documents/${id}`, {
        method: 'DELETE',
        headers: authHeaders(token),
      });
      await loadDocs();
    } catch (err) {
      setDocsErr(formatApiError(err));
    }
  }

  async function onSaveConnector(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !canManageConnector(role)) return;
    setConnMsg(null);
    try {
      const body: Record<string, string | null> = {
        external_hospital_base_url: connBase.trim() || null,
      };
      if (connKey.trim().length > 0) {
        body.external_hospital_api_key = connKey.trim();
      }
      const c = await apiFetch<TenantConnector>('/api/v1/admin/tenant-connector', {
        method: 'PATCH',
        headers: authHeaders(token),
        json: body,
      });
      setConnector(c);
      setConnKey('');
      setConnMsg('Kaydedildi.');
    } catch (err) {
      setConnMsg(formatApiError(err));
    }
  }

  async function onClearConnectorKey() {
    if (!token || !canManageConnector(role)) return;
    setConnMsg(null);
    try {
      const c = await apiFetch<TenantConnector>('/api/v1/admin/tenant-connector', {
        method: 'PATCH',
        headers: authHeaders(token),
        json: { external_hospital_api_key: null },
      });
      setConnector(c);
      setConnMsg('API anahtarı temizlendi.');
    } catch (err) {
      setConnMsg(formatApiError(err));
    }
  }

  if (!token || !me) {
    return (
      <div className="min-h-screen bg-slate-50 py-12">
        <LoginForm
          onSuccess={(access, user) => {
            setSession(access, user);
          }}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">HospitAI Admin</h1>
            <p className="text-sm text-slate-600">
              {me.email} · rol: <span className="font-medium">{me.role}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={() => void onLogout()}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          >
            Çıkış
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-8 px-4 py-8">
        <RoleBanner role={role} />

        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-slate-900">RAG dokümanları</h2>
            <button
              type="button"
              onClick={() => void loadDocs()}
              className="text-sm text-sky-700 hover:underline"
            >
              Yenile
            </button>
          </div>
          {docsErr && <p className="mt-2 text-sm text-red-700">{docsErr}</p>}
          <ul className="mt-4 divide-y divide-slate-100">
            {docs.length === 0 && !docsErr && (
              <li className="py-6 text-center text-sm text-slate-500">Henüz doküman yok.</li>
            )}
            {docs.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div>
                  <p className="font-medium text-slate-900">{d.title}</p>
                  <p className="text-xs text-slate-500">
                    {d.source_type} · {d.status} · {d.chunk_count} parça ·{' '}
                    {new Date(d.created_at).toLocaleString()}
                  </p>
                </div>
                {canManageDocuments(role) && (
                  <button
                    type="button"
                    onClick={() => void onDelete(d.id)}
                    className="rounded border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
                  >
                    Sil
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>

        {canManageDocuments(role) && (
          <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-base font-semibold text-slate-900">Metin yükle</h2>
            <form onSubmit={onIngest} className="mt-4 space-y-3">
              <label className="block text-sm font-medium text-slate-700">
                Başlık
                <input
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900"
                  value={ingestTitle}
                  onChange={(e) => setIngestTitle(e.target.value)}
                  required
                  maxLength={512}
                />
              </label>
              <label className="block text-sm font-medium text-slate-700">
                Kaynak tipi
                <input
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900"
                  value={ingestSource}
                  onChange={(e) => setIngestSource(e.target.value)}
                  maxLength={64}
                />
              </label>
              <label className="block text-sm font-medium text-slate-700">
                İçerik
                <textarea
                  className="mt-1 min-h-[140px] w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900"
                  value={ingestContent}
                  onChange={(e) => setIngestContent(e.target.value)}
                  required
                />
              </label>
              {ingestMsg && <p className="text-sm text-slate-600">{ingestMsg}</p>}
              <button
                type="submit"
                className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
              >
                Yükle
              </button>
            </form>
          </section>
        )}

        {canManageConnector(role) && (
          <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-base font-semibold text-slate-900">Dış hastane bağlantısı</h2>
            <p className="mt-1 text-sm text-slate-600">
              Tenant için harici randevu API adresi ve isteğe bağlı API anahtarı. Anahtar yalnızca
              kayıtlı mı bilgisi gösterilir; düz metin olarak saklanmaz / gösterilmez.
            </p>
            {connector && (
              <p className="mt-2 text-sm text-slate-700">
                Kayıtlı API anahtarı:{' '}
                <span className="font-medium">
                  {connector.has_external_hospital_api_key ? 'var' : 'yok'}
                </span>
              </p>
            )}
            <form onSubmit={onSaveConnector} className="mt-4 space-y-3">
              <label className="block text-sm font-medium text-slate-700">
                Base URL
                <input
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm text-slate-900"
                  value={connBase}
                  onChange={(e) => setConnBase(e.target.value)}
                  placeholder="https://hospital-api.example.com"
                />
              </label>
              <label className="block text-sm font-medium text-slate-700">
                API anahtarı (yalnızca değiştirmek için doldurun)
                <input
                  type="password"
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm text-slate-900"
                  value={connKey}
                  onChange={(e) => setConnKey(e.target.value)}
                  autoComplete="off"
                />
              </label>
              {connMsg && <p className="text-sm text-slate-600">{connMsg}</p>}
              <div className="flex flex-wrap gap-2">
                <button
                  type="submit"
                  className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
                >
                  Kaydet
                </button>
                <button
                  type="button"
                  onClick={() => void onClearConnectorKey()}
                  className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                >
                  Anahtarı temizle
                </button>
              </div>
            </form>
          </section>
        )}
      </main>
    </div>
  );
}
