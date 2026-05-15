import { useCallback, useEffect, useState } from 'react';

import { apiFetch, formatApiError } from '@/lib/api';
import {
  authHeaders,
  canManageConnector,
  canManageDocuments,
  canTenantAdmin,
  fetchMe,
  useAuth,
  type Me,
  type UserRole,
} from '@/store/auth';

/* ─── Types ──────────────────────────────────────────────────────────────── */
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
  content?: string | null;
};
type DocumentListResponse = { documents: DocumentRow[] };
type TenantConnector = {
  external_hospital_base_url: string | null;
  has_external_hospital_api_key: boolean;
};
type AdminUserRow = {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
};
type AdminUsersResponse = { users: AdminUserRow[] };
type TenantPolicy = { rag_retrieval_enabled: boolean };
type TenantAgentLLM = {
  agent_llm_temperature: number | null;
  agent_llm_model: string | null;
  agent_max_conversation_history: number | null;
};
type ReindexQueuedResponse = { task_id: string; document_id: string };
type AppointmentRow = {
  id: string;
  starts_at: string;
  ends_at: string;
  status: string;
  patient_user_id: string | null;
  doctor_name: string | null;
  department_name: string | null;
  guest_display_name: string | null;
  guest_contact: string | null;
  notes: string | null;
};
type TicketRow = {
  id: string;
  reference: string;
  subject: string;
  description: string;
  status: string;
  priority: string;
  category: string | null;
  created_at: string;
};

type DoctorRow = {
  id: string;
  full_name: string;
  title: string | null;
  specialty: string | null;
  is_active: boolean;
  department_id: string | null;
  department_name: string | null;
};
type DaySlotRow = {
  starts_at: string;
  ends_at: string;
  time_start: string;
  label: string;
  state: 'free' | 'blocked' | 'booked';
  block_id: string | null;
};

type TabId = 'dashboard' | 'appointments' | 'tickets' | 'doctors' | 'llm' | 'rag' | 'settings';

/* ─── Helpers ─────────────────────────────────────────────────────────────── */
const STATUS_COLORS: Record<string, string> = {
  confirmed: 'bg-green-100 text-green-800',
  cancelled: 'bg-red-100 text-red-700',
  pending: 'bg-yellow-100 text-yellow-800',
  open: 'bg-sky-100 text-sky-800',
  resolved: 'bg-green-100 text-green-800',
  closed: 'bg-slate-100 text-slate-600',
};
function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status] ?? 'bg-slate-100 text-slate-700'}`}
    >
      {status}
    </span>
  );
}
function fmtDate(iso: string) {
  return new Date(iso).toLocaleString('tr-TR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
function SectionCard({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        {action}
      </div>
      <div className="px-6 py-4">{children}</div>
    </div>
  );
}

/* ─── Config from env ─────────────────────────────────────────────────────── */
const TENANT_SLUG = (import.meta.env.VITE_TENANT_SLUG as string | undefined) ?? 'demo-hospital';

/* ─── Login ───────────────────────────────────────────────────────────────── */
function LoginForm({
  onSuccess,
  hospitalName,
}: {
  onSuccess: (access: string, me: Me) => void;
  hospitalName: string;
}) {
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
        json: { tenant_slug: TENANT_SLUG, email: email.trim(), password },
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
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-100 to-sky-50 p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-2xl border border-slate-200 bg-white p-8 shadow-lg"
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-sky-500 to-teal-500 flex items-center justify-center flex-shrink-0">
            <svg
              className="w-5 h-5 text-white"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
              />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900">{hospitalName}</h1>
            <p className="text-xs text-slate-500">HospitAI Admin Paneli</p>
          </div>
        </div>
        {err && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {err}
          </div>
        )}
        <label className="block text-sm font-medium text-slate-700">
          E-posta
          <input
            type="email"
            autoComplete="username"
            required
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Şifre
          <input
            type="password"
            autoComplete="current-password"
            required
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-gradient-to-r from-sky-500 to-teal-500 px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60 transition-opacity"
        >
          {loading ? 'Giriş yapılıyor…' : 'Giriş Yap'}
        </button>
      </form>
    </div>
  );
}

/* ─── Main App ────────────────────────────────────────────────────────────── */
export default function App() {
  const accessToken = useAuth((s) => s.accessToken);
  const me = useAuth((s) => s.me);
  const setSession = useAuth((s) => s.setSession);
  const clear = useAuth((s) => s.clear);

  const [activeTab, setActiveTab] = useState<TabId>('dashboard');

  // Appointments
  const [appointments, setAppointments] = useState<AppointmentRow[]>([]);
  const [apptsErr, setApptsErr] = useState<string | null>(null);
  const [apptsLoading, setApptsLoading] = useState(false);
  const [apptFilter, setApptFilter] = useState<string>('all');

  // Tickets
  const [tickets, setTickets] = useState<TicketRow[]>([]);
  const [ticketsErr, setTicketsErr] = useState<string | null>(null);
  const [ticketsLoading, setTicketsLoading] = useState(false);
  const [ticketFilter, setTicketFilter] = useState<string>('all');

  // Docs
  const [docs, setDocs] = useState<DocumentRow[]>([]);
  const [docsErr, setDocsErr] = useState<string | null>(null);
  const [ingestTitle, setIngestTitle] = useState('');
  const [ingestContent, setIngestContent] = useState('');
  const [ingestSource, setIngestSource] = useState('manual');
  const [ingestMsg, setIngestMsg] = useState<string | null>(null);
  const [reindexHint, setReindexHint] = useState<string | null>(null);
  const [editDoc, setEditDoc] = useState<DocumentRow | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');
  const [editDocErr, setEditDocErr] = useState<string | null>(null);
  const [editDocLoading, setEditDocLoading] = useState(false);

  // Connector
  const [connector, setConnector] = useState<TenantConnector | null>(null);
  const [connBase, setConnBase] = useState('');
  const [connKey, setConnKey] = useState('');
  const [connMsg, setConnMsg] = useState<string | null>(null);

  // Users
  const [adminUsers, setAdminUsers] = useState<AdminUserRow[]>([]);
  const [adminUsersErr, setAdminUsersErr] = useState<string | null>(null);
  const [userAdminMsg, setUserAdminMsg] = useState<string | null>(null);

  // Doctors
  const [doctors, setDoctors] = useState<DoctorRow[]>([]);
  const [doctorsErr, setDoctorsErr] = useState<string | null>(null);
  const [doctorsLoading, setDoctorsLoading] = useState(false);
  const [doctorFormOpen, setDoctorFormOpen] = useState(false);
  const [doctorEdit, setDoctorEdit] = useState<DoctorRow | null>(null);
  const [doctorFormName, setDoctorFormName] = useState('');
  const [doctorFormTitle, setDoctorFormTitle] = useState('');
  const [doctorFormDeptName, setDoctorFormDeptName] = useState('');
  const [doctorFormMsg, setDoctorFormMsg] = useState<string | null>(null);
  // Day slot grid (admin)
  const [blockedSlotDoctor, setBlockedSlotDoctor] = useState<DoctorRow | null>(null);
  const [blockedSlotDay, setBlockedSlotDay] = useState('');
  const [daySlots, setDaySlots] = useState<DaySlotRow[]>([]);
  const [daySlotsErr, setDaySlotsErr] = useState<string | null>(null);

  // Hospital name (from backend)
  const [hospitalName, setHospitalName] = useState('Hospital');
  const [hospitalNameInput, setHospitalNameInput] = useState('');
  const [hospitalNameMsg, setHospitalNameMsg] = useState<string | null>(null);

  // Giriş öncesi: public tenant adı (LoginForm prop'u; accessToken yokken çalışır)
  useEffect(() => {
    if (accessToken) return;
    let cancelled = false;
    void fetch(`/api/v1/public/tenant-info?slug=${encodeURIComponent(TENANT_SLUG)}`)
      .then((r) => r.json())
      .then((d: { name?: string }) => {
        if (!cancelled && typeof d?.name === 'string' && d.name.trim()) {
          setHospitalName(d.name.trim());
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  // Policy + LLM
  const [tenantPolicy, setTenantPolicy] = useState<TenantPolicy | null>(null);
  const [policyErr, setPolicyErr] = useState<string | null>(null);
  const [policyMsg, setPolicyMsg] = useState<string | null>(null);
  const [agentLlmTemp, setAgentLlmTemp] = useState('');
  const [agentLlmModel, setAgentLlmModel] = useState('');
  const [agentLlmHist, setAgentLlmHist] = useState('');
  const [agentLlmErr, setAgentLlmErr] = useState<string | null>(null);
  const [agentLlmMsg, setAgentLlmMsg] = useState<string | null>(null);

  const token = accessToken;
  const role = me?.role;

  /* ── Data loaders ───────────────────────────────────────────────────────── */
  const loadAppointments = useCallback(async () => {
    if (!token) return;
    setApptsLoading(true);
    setApptsErr(null);
    try {
      const rows = await apiFetch<AppointmentRow[]>('/api/v1/appointments?limit=100', {
        headers: authHeaders(token),
      });
      setAppointments(rows);
    } catch (e) {
      setApptsErr(formatApiError(e));
    } finally {
      setApptsLoading(false);
    }
  }, [token]);

  const loadTickets = useCallback(async () => {
    if (!token) return;
    setTicketsLoading(true);
    setTicketsErr(null);
    try {
      const rows = await apiFetch<TicketRow[]>('/api/v1/tickets?limit=100', {
        headers: authHeaders(token),
      });
      setTickets(rows);
    } catch (e) {
      setTicketsErr(formatApiError(e));
    } finally {
      setTicketsLoading(false);
    }
  }, [token]);

  const loadDoctors = useCallback(async () => {
    if (!token) return;
    setDoctorsLoading(true);
    setDoctorsErr(null);
    try {
      const docs = await apiFetch<DoctorRow[]>('/api/v1/admin/doctors', {
        headers: authHeaders(token),
      });
      setDoctors(docs);
    } catch (e) {
      setDoctorsErr(formatApiError(e));
    } finally {
      setDoctorsLoading(false);
    }
  }, [token]);

  const loadDaySlots = useCallback(
    async (doctorId: string, day: string) => {
      if (!token) return;
      setDaySlotsErr(null);
      try {
        const rows = await apiFetch<DaySlotRow[]>(
          `/api/v1/admin/doctors/${doctorId}/day-slots?day=${day}`,
          { headers: authHeaders(token) }
        );
        setDaySlots(rows);
      } catch (e) {
        setDaySlotsErr(formatApiError(e));
      }
    },
    [token]
  );

  const loadDocs = useCallback(async () => {
    if (!token) return;
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

  const loadAdminUsers = useCallback(async () => {
    if (!token || !canTenantAdmin(role)) return;
    try {
      const res = await apiFetch<AdminUsersResponse>('/api/v1/admin/users', {
        headers: authHeaders(token),
      });
      setAdminUsers(res.users);
    } catch (e) {
      setAdminUsersErr(formatApiError(e));
    }
  }, [token, role]);

  const loadHospitalName = useCallback(async () => {
    if (!token) return;
    try {
      const r = await apiFetch<{ name: string; slug: string }>('/api/v1/admin/tenant-name', {
        headers: authHeaders(token),
      });
      setHospitalName(r.name);
      setHospitalNameInput(r.name);
    } catch {
      /* silent */
    }
  }, [token]);

  const loadTenantPolicy = useCallback(async () => {
    if (!token || !canTenantAdmin(role)) return;
    try {
      const p = await apiFetch<TenantPolicy>('/api/v1/admin/tenant-policy', {
        headers: authHeaders(token),
      });
      setTenantPolicy(p);
    } catch (e) {
      setPolicyErr(formatApiError(e));
    }
  }, [token, role]);

  const loadTenantAgentLlm = useCallback(async () => {
    if (!token || !canTenantAdmin(role)) return;
    try {
      const a = await apiFetch<TenantAgentLLM>('/api/v1/admin/tenant-agent-llm', {
        headers: authHeaders(token),
      });
      setAgentLlmTemp(a.agent_llm_temperature != null ? String(a.agent_llm_temperature) : '');
      setAgentLlmModel(a.agent_llm_model ?? '');
      setAgentLlmHist(
        a.agent_max_conversation_history != null ? String(a.agent_max_conversation_history) : ''
      );
    } catch (e) {
      setAgentLlmErr(formatApiError(e));
    }
  }, [token, role]);

  useEffect(() => {
    if (!token) return;
    void loadAppointments();
    void loadTickets();
    void loadDocs();
    void loadHospitalName();
    void loadDoctors();
    if (canManageConnector(role)) void loadConnector();
    if (canTenantAdmin(role)) {
      void loadAdminUsers();
      void loadTenantPolicy();
      void loadTenantAgentLlm();
    }
  }, [
    token,
    role,
    loadAppointments,
    loadTickets,
    loadDocs,
    loadConnector,
    loadAdminUsers,
    loadTenantPolicy,
    loadTenantAgentLlm,
    loadHospitalName,
    loadDoctors,
  ]);

  // Auto-logout when any API call returns 401
  useEffect(() => {
    function handleAuthExpiry() {
      clear();
    }
    window.addEventListener('auth:logout', handleAuthExpiry);
    return () => window.removeEventListener('auth:logout', handleAuthExpiry);
  }, [clear]);

  /* ── Doctor actions ─────────────────────────────────────────────────────── */
  function openNewDoctorForm() {
    setDoctorEdit(null);
    setDoctorFormName('');
    setDoctorFormTitle('');
    setDoctorFormDeptName('');
    setDoctorFormMsg(null);
    setDoctorFormOpen(true);
  }

  function openEditDoctorForm(doc: DoctorRow) {
    setDoctorEdit(doc);
    setDoctorFormName(doc.full_name);
    setDoctorFormTitle(doc.title ?? '');
    setDoctorFormDeptName(doc.department_name ?? '');
    setDoctorFormMsg(null);
    setDoctorFormOpen(true);
  }

  async function onSaveDoctor(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setDoctorFormMsg(null);
    const dept = doctorFormDeptName.trim();
    try {
      if (doctorEdit) {
        await apiFetch(`/api/v1/admin/doctors/${doctorEdit.id}`, {
          method: 'PATCH',
          headers: authHeaders(token),
          json: {
            full_name: doctorFormName,
            title: doctorFormTitle || null,
            department_name: dept || null,
          },
        });
      } else {
        await apiFetch('/api/v1/admin/doctors', {
          method: 'POST',
          headers: authHeaders(token),
          json: {
            full_name: doctorFormName,
            title: doctorFormTitle || null,
            department_name: dept || null,
          },
        });
      }
      setDoctorFormOpen(false);
      await loadDoctors();
    } catch (e) {
      setDoctorFormMsg(formatApiError(e));
    }
  }

  async function onToggleDoctorActive(doc: DoctorRow) {
    if (!token) return;
    try {
      await apiFetch(`/api/v1/admin/doctors/${doc.id}`, {
        method: 'PATCH',
        headers: authHeaders(token),
        json: { is_active: !doc.is_active },
      });
      await loadDoctors();
    } catch (e) {
      setDoctorsErr(formatApiError(e));
    }
  }

  async function onOpenBlockedSlots(doc: DoctorRow) {
    const today = new Date().toISOString().split('T')[0];
    setBlockedSlotDoctor(doc);
    setBlockedSlotDay(today);
    setDaySlotsErr(null);
    await loadDaySlots(doc.id, today);
  }

  async function onDaySlotCellClick(sl: DaySlotRow) {
    if (!token || !blockedSlotDoctor) return;
    if (sl.state === 'booked') return;
    setDaySlotsErr(null);
    try {
      if (sl.state === 'free') {
        await apiFetch(`/api/v1/admin/doctors/${blockedSlotDoctor.id}/blocked-slots`, {
          method: 'POST',
          headers: authHeaders(token),
          json: { date: blockedSlotDay, time: sl.time_start },
        });
      } else if (sl.state === 'blocked' && sl.block_id) {
        await apiFetch(
          `/api/v1/admin/doctors/${blockedSlotDoctor.id}/blocked-slots/${sl.block_id}`,
          { method: 'DELETE', headers: authHeaders(token) }
        );
      }
      await loadDaySlots(blockedSlotDoctor.id, blockedSlotDay);
    } catch (e) {
      setDaySlotsErr(formatApiError(e));
    }
  }

  /* ── Actions ────────────────────────────────────────────────────────────── */
  async function onCancelAppointment(id: string) {
    if (!token || !window.confirm('Bu randevuyu iptal etmek istiyor musunuz?')) return;
    try {
      await apiFetch(`/api/v1/appointments/${id}/cancel`, {
        method: 'POST',
        headers: authHeaders(token),
      });
      await loadAppointments();
    } catch (e) {
      setApptsErr(formatApiError(e));
    }
  }

  async function onCloseTicket(ref: string) {
    if (!token || !window.confirm(`${ref} talebini kapatmak istiyor musunuz?`)) return;
    try {
      await apiFetch(`/api/v1/tickets/${ref}/close`, {
        method: 'PATCH',
        headers: authHeaders(token),
      });
      await loadTickets();
    } catch (e) {
      setTicketsErr(formatApiError(e));
    }
  }

  async function onLogout() {
    clear();
    setAppointments([]);
    setTickets([]);
    setDocs([]);
    setConnector(null);
    setAdminUsers([]);
    setTenantPolicy(null);
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
    if (!token || !canManageDocuments(role) || !window.confirm('Sil?')) return;
    try {
      await apiFetch(`/api/v1/documents/${id}`, { method: 'DELETE', headers: authHeaders(token) });
      await loadDocs();
    } catch (err) {
      setDocsErr(formatApiError(err));
    }
  }

  async function onReindexEmbeddings(docId: string) {
    if (!token || !canManageDocuments(role)) return;
    try {
      const r = await apiFetch<ReindexQueuedResponse>(
        `/api/v1/documents/${docId}/reindex-embeddings`,
        { method: 'POST', headers: authHeaders(token) }
      );
      setReindexHint(`Embedding kuyruğu: ${r.task_id.slice(0, 10)}…`);
    } catch (e) {
      setDocsErr(formatApiError(e));
    }
  }

  async function openEditDocument(id: string) {
    if (!token || !canManageDocuments(role)) return;
    setEditDocLoading(true);
    setEditDocErr(null);
    try {
      const d = await apiFetch<DocumentRow>(`/api/v1/documents/${id}`, {
        headers: authHeaders(token),
      });
      setEditDoc(d);
      setEditTitle(d.title);
      setEditContent(d.content ?? '');
    } catch (e) {
      setDocsErr(`Doküman yüklenemedi: ${formatApiError(e)}`);
    } finally {
      setEditDocLoading(false);
    }
  }

  async function onSaveEditDocument(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !editDoc || !canManageDocuments(role)) return;
    setEditDocErr(null);
    if (!editContent.trim()) {
      setEditDocErr('İçerik boş olamaz.');
      return;
    }
    try {
      await apiFetch(`/api/v1/documents/${editDoc.id}`, {
        method: 'PATCH',
        headers: authHeaders(token),
        json: { title: editTitle.trim(), content: editContent },
      });
      setEditDoc(null);
      setReindexHint('Doküman güncellendi; metin yeniden parçalandı ve vektörler yenilendi.');
      await loadDocs();
    } catch (e) {
      setEditDocErr(formatApiError(e));
    }
  }

  async function onSaveConnector(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !canManageConnector(role)) return;
    try {
      const body: Record<string, string | null> = {
        external_hospital_base_url: connBase.trim() || null,
      };
      if (connKey.trim()) body.external_hospital_api_key = connKey.trim();
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

  async function onToggleRagPolicy(enabled: boolean) {
    if (!token || !canTenantAdmin(role)) return;
    try {
      const p = await apiFetch<TenantPolicy>('/api/v1/admin/tenant-policy', {
        method: 'PATCH',
        headers: authHeaders(token),
        json: { rag_retrieval_enabled: enabled },
      });
      setTenantPolicy(p);
      setPolicyMsg('Güncellendi.');
    } catch (e) {
      setPolicyErr(formatApiError(e));
    }
  }

  async function onSaveAgentLlm(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !canTenantAdmin(role)) return;
    setAgentLlmMsg(null);
    setAgentLlmErr(null);
    const json: Record<string, number | string> = {};
    const t = agentLlmTemp.trim();
    if (t) {
      const n = Number(t);
      if (isNaN(n)) {
        setAgentLlmErr('Geçersiz sayı.');
        return;
      }
      json.agent_llm_temperature = n;
    }
    const m = agentLlmModel.trim();
    if (m) json.agent_llm_model = m;
    const h = agentLlmHist.trim();
    if (h) {
      const n = parseInt(h, 10);
      if (isNaN(n)) {
        setAgentLlmErr('Tam sayı girin.');
        return;
      }
      json.agent_max_conversation_history = n;
    }
    if (!Object.keys(json).length) {
      setAgentLlmErr('En az bir alan doldurun.');
      return;
    }
    try {
      await apiFetch<TenantAgentLLM>('/api/v1/admin/tenant-agent-llm', {
        method: 'PATCH',
        headers: authHeaders(token),
        json,
      });
      setAgentLlmMsg('LLM ayarları güncellendi.');
    } catch (err) {
      setAgentLlmErr(formatApiError(err));
    }
  }

  async function onSaveHospitalName(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setHospitalNameMsg(null);
    try {
      const r = await apiFetch<{ name: string }>('/api/v1/admin/tenant-name', {
        method: 'PATCH',
        headers: authHeaders(token),
        json: { name: hospitalNameInput.trim() },
      });
      setHospitalName(r.name);
      setHospitalNameMsg('Hastane adı güncellendi.');
    } catch (e) {
      setHospitalNameMsg(formatApiError(e));
    }
  }

  async function onPatchUser(userId: string, patch: { role?: UserRole; is_active?: boolean }) {
    if (!token || !canTenantAdmin(role)) return;
    try {
      await apiFetch(`/api/v1/admin/users/${userId}`, {
        method: 'PATCH',
        headers: authHeaders(token),
        json: patch,
      });
      setUserAdminMsg('Güncellendi.');
      await loadAdminUsers();
    } catch (e) {
      setUserAdminMsg(formatApiError(e));
    }
  }

  /* ── Auth guard ──────────────────────────────────────────────────────────── */
  if (!token || !me)
    return (
      <LoginForm
        onSuccess={(access, user) => setSession(access, user)}
        hospitalName={hospitalName}
      />
    );

  /* ── Stats for dashboard ─────────────────────────────────────────────────── */
  const totalAppts = appointments.length;
  const confirmedAppts = appointments.filter((a) => a.status === 'confirmed').length;
  const cancelledAppts = appointments.filter((a) => a.status === 'cancelled').length;
  const openTickets = tickets.filter((t) => t.status === 'open').length;
  const closedTickets = tickets.filter(
    (t) => t.status === 'closed' || t.status === 'resolved'
  ).length;

  const filteredAppts =
    apptFilter === 'all' ? appointments : appointments.filter((a) => a.status === apptFilter);
  const filteredTickets =
    ticketFilter === 'all' ? tickets : tickets.filter((t) => t.status === ticketFilter);

  /* ── Sidebar nav config ─────────────────────────────────────────────────── */
  const NAV_ITEMS: { id: TabId; label: string; badge?: number; icon: React.ReactNode }[] = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
          />
        </svg>
      ),
    },
    {
      id: 'appointments',
      label: 'Randevular',
      badge: confirmedAppts,
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
          />
        </svg>
      ),
    },
    {
      id: 'tickets',
      label: 'Şikayetler',
      badge: openTickets,
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"
          />
        </svg>
      ),
    },
    {
      id: 'doctors',
      label: 'Doktorlar',
      badge: doctors.filter((d) => d.is_active).length || undefined,
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      ),
    },
    {
      id: 'llm',
      label: 'LLM Ayarları',
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2h-2"
          />
        </svg>
      ),
    },
    {
      id: 'rag',
      label: 'RAG / Dokümanlar',
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
      ),
    },
    {
      id: 'settings',
      label: 'Ayarlar',
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
          />
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      ),
    },
  ];

  const TAB_TITLES: Record<TabId, string> = {
    dashboard: 'Dashboard',
    appointments: 'Randevular',
    tickets: 'Şikayet / Talepler',
    doctors: 'Doktorlar',
    llm: 'LLM Ayarları',
    rag: 'RAG / Dokümanlar',
    settings: 'Ayarlar',
  };

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* ── Dark Sidebar ─────────────────────────────────────────────────────── */}
      <aside className="w-60 flex-shrink-0 bg-slate-900 flex flex-col overflow-y-auto">
        {/* Brand */}
        <div className="px-5 py-5 border-b border-slate-700/60">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-sky-500 to-teal-500 flex items-center justify-center flex-shrink-0 shadow-lg">
              <svg
                className="w-5 h-5 text-white"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
                />
              </svg>
            </div>
            <div className="min-w-0">
              <p className="text-sm font-bold text-white truncate">{hospitalName}</p>
              <p className="text-[11px] text-slate-400 truncate">HospitAI Admin</p>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const active = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                  active
                    ? 'bg-sky-500/20 text-sky-300 shadow-sm'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
                }`}
              >
                <span
                  className={active ? 'text-sky-400' : 'text-slate-500 group-hover:text-slate-300'}
                >
                  {item.icon}
                </span>
                <span className="flex-1 text-left">{item.label}</span>
                {item.badge != null && item.badge > 0 && (
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold leading-none ${active ? 'bg-sky-500 text-white' : 'bg-slate-700 text-slate-300'}`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* User area at bottom */}
        <div className="px-4 py-4 border-t border-slate-700/60">
          <div className="flex items-center gap-2.5 mb-3">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sky-500 to-teal-500 flex items-center justify-center flex-shrink-0 text-xs font-bold text-white">
              {(me.email?.[0] ?? 'A').toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-slate-200 truncate">{me.email}</p>
              <span className="text-[10px] text-sky-400 font-medium">{me.role}</span>
            </div>
          </div>
          <button
            onClick={() => void onLogout()}
            className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
              />
            </svg>
            Çıkış Yap
          </button>
        </div>
      </aside>

      {/* ── Content area ─────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex-shrink-0 border-b border-slate-200 bg-white px-6 py-3.5 flex items-center justify-between shadow-sm">
          <h1 className="text-base font-semibold text-slate-800">{TAB_TITLES[activeTab]}</h1>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="w-2 h-2 rounded-full bg-green-400 inline-block"></span>
            Sistem aktif
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {/* ══ DASHBOARD ══════════════════════════════════════════════════════ */}
          {activeTab === 'dashboard' && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
                {[
                  {
                    label: 'Toplam Randevu',
                    value: totalAppts,
                    color: 'text-slate-900',
                    bg: 'bg-white',
                  },
                  {
                    label: 'Onaylı',
                    value: confirmedAppts,
                    color: 'text-green-700',
                    bg: 'bg-green-50',
                  },
                  { label: 'İptal', value: cancelledAppts, color: 'text-red-600', bg: 'bg-red-50' },
                  {
                    label: 'Açık Talep',
                    value: openTickets,
                    color: 'text-sky-700',
                    bg: 'bg-sky-50',
                  },
                  {
                    label: 'Kapalı Talep',
                    value: closedTickets,
                    color: 'text-slate-600',
                    bg: 'bg-slate-100',
                  },
                ].map((s) => (
                  <div
                    key={s.label}
                    className={`rounded-xl border border-slate-200 ${s.bg} p-4 shadow-sm`}
                  >
                    <p className="text-xs font-medium text-slate-500">{s.label}</p>
                    <p className={`mt-1 text-3xl font-bold ${s.color}`}>{s.value}</p>
                  </div>
                ))}
              </div>

              {(apptsErr || ticketsErr) && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex items-center gap-2">
                  <svg
                    className="w-4 h-4 flex-shrink-0"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  {apptsErr || ticketsErr}
                </div>
              )}

              <div className="grid lg:grid-cols-2 gap-6">
                <SectionCard
                  title="Son Randevular"
                  action={
                    <button
                      onClick={() => setActiveTab('appointments')}
                      className="text-xs text-sky-600 hover:underline"
                    >
                      Tümünü gör →
                    </button>
                  }
                >
                  <ul className="divide-y divide-slate-100">
                    {appointments.slice(0, 5).map((a) => (
                      <li key={a.id} className="py-2.5 flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-slate-800 truncate">
                            {a.guest_display_name ?? 'Kayıtlı hasta'}
                          </p>
                          <p className="text-xs text-slate-500">
                            {a.doctor_name ?? '—'} · {fmtDate(a.starts_at)}
                          </p>
                        </div>
                        <StatusBadge status={a.status} />
                      </li>
                    ))}
                    {appointments.length === 0 && (
                      <li className="py-4 text-center text-sm text-slate-400">Randevu yok</li>
                    )}
                  </ul>
                </SectionCard>

                <SectionCard
                  title="Son Talepler"
                  action={
                    <button
                      onClick={() => setActiveTab('tickets')}
                      className="text-xs text-sky-600 hover:underline"
                    >
                      Tümünü gör →
                    </button>
                  }
                >
                  <ul className="divide-y divide-slate-100">
                    {tickets.slice(0, 5).map((t) => (
                      <li key={t.id} className="py-2.5 flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-slate-800 truncate">{t.subject}</p>
                          <p className="text-xs text-slate-500">
                            {t.reference} · {fmtDate(t.created_at)}
                          </p>
                        </div>
                        <StatusBadge status={t.status} />
                      </li>
                    ))}
                    {tickets.length === 0 && (
                      <li className="py-4 text-center text-sm text-slate-400">Talep yok</li>
                    )}
                  </ul>
                </SectionCard>
              </div>
            </>
          )}

          {/* ══ APPOINTMENTS ═══════════════════════════════════════════════════ */}
          {activeTab === 'appointments' && (
            <SectionCard
              title={`Randevular (${filteredAppts.length})`}
              action={
                <div className="flex items-center gap-2">
                  <select
                    value={apptFilter}
                    onChange={(e) => setApptFilter(e.target.value)}
                    className="rounded-lg border border-slate-300 px-2 py-1 text-xs"
                  >
                    <option value="all">Tümü</option>
                    <option value="confirmed">Onaylı</option>
                    <option value="cancelled">İptal</option>
                    <option value="pending">Bekliyor</option>
                  </select>
                  <button
                    onClick={() => void loadAppointments()}
                    className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                  >
                    ↺ Yenile
                  </button>
                </div>
              }
            >
              {apptsLoading && (
                <p className="py-4 text-center text-sm text-slate-400">Yükleniyor…</p>
              )}
              {apptsErr && <p className="text-sm text-red-600 mb-3">{apptsErr}</p>}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">
                      <th className="py-2 pr-4">Hasta</th>
                      <th className="py-2 pr-4">Doktor</th>
                      <th className="py-2 pr-4">Bölüm</th>
                      <th className="py-2 pr-4">Tarih</th>
                      <th className="py-2 pr-4">Durum</th>
                      <th className="py-2">İşlem</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {filteredAppts.map((a) => (
                      <tr key={a.id} className="hover:bg-slate-50/60 transition-colors">
                        <td className="py-3 pr-4">
                          <p className="font-medium text-slate-800">
                            {a.guest_display_name ?? '—'}
                          </p>
                          {a.guest_contact && (
                            <p className="text-xs text-slate-400">{a.guest_contact}</p>
                          )}
                        </td>
                        <td className="py-3 pr-4 text-slate-700">{a.doctor_name ?? '—'}</td>
                        <td className="py-3 pr-4 text-slate-500">{a.department_name ?? '—'}</td>
                        <td className="py-3 pr-4 text-slate-600 whitespace-nowrap">
                          {fmtDate(a.starts_at)}
                        </td>
                        <td className="py-3 pr-4">
                          <StatusBadge status={a.status} />
                        </td>
                        <td className="py-3">
                          {a.status === 'confirmed' && (
                            <button
                              onClick={() => void onCancelAppointment(a.id)}
                              className="rounded border border-red-200 px-2 py-1 text-xs text-red-600 hover:bg-red-50 transition-colors"
                            >
                              İptal et
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {filteredAppts.length === 0 && !apptsLoading && (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-sm text-slate-400">
                          Randevu bulunamadı.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </SectionCard>
          )}

          {/* ══ TICKETS ════════════════════════════════════════════════════════ */}
          {activeTab === 'tickets' && (
            <SectionCard
              title={`Şikayet / Talepler (${filteredTickets.length})`}
              action={
                <div className="flex items-center gap-2">
                  <select
                    value={ticketFilter}
                    onChange={(e) => setTicketFilter(e.target.value)}
                    className="rounded-lg border border-slate-300 px-2 py-1 text-xs"
                  >
                    <option value="all">Tümü</option>
                    <option value="open">Açık</option>
                    <option value="resolved">Çözüldü</option>
                    <option value="closed">Kapalı</option>
                  </select>
                  <button
                    onClick={() => void loadTickets()}
                    className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                  >
                    ↺ Yenile
                  </button>
                </div>
              }
            >
              {ticketsLoading && (
                <p className="py-4 text-center text-sm text-slate-400">Yükleniyor…</p>
              )}
              {ticketsErr && <p className="text-sm text-red-600 mb-3">{ticketsErr}</p>}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">
                      <th className="py-2 pr-4">Referans</th>
                      <th className="py-2 pr-4">Konu</th>
                      <th className="py-2 pr-4">Öncelik</th>
                      <th className="py-2 pr-4">Tarih</th>
                      <th className="py-2 pr-4">Durum</th>
                      <th className="py-2">İşlem</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {filteredTickets.map((t) => (
                      <tr key={t.id} className="hover:bg-slate-50/60 transition-colors">
                        <td className="py-3 pr-4 font-mono text-xs text-slate-600">
                          {t.reference}
                        </td>
                        <td className="py-3 pr-4 max-w-sm">
                          <p className="font-medium text-slate-800">{t.subject}</p>
                          <p className="text-xs text-slate-400 whitespace-pre-wrap break-words">
                            {t.description}
                          </p>
                        </td>
                        <td className="py-3 pr-4">
                          <span
                            className={`text-xs font-medium ${t.priority === 'high' ? 'text-red-600' : t.priority === 'medium' ? 'text-yellow-700' : 'text-slate-500'}`}
                          >
                            {t.priority}
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-slate-500 whitespace-nowrap text-xs">
                          {fmtDate(t.created_at)}
                        </td>
                        <td className="py-3 pr-4">
                          <StatusBadge status={t.status} />
                        </td>
                        <td className="py-3">
                          {t.status === 'open' && (
                            <button
                              onClick={() => void onCloseTicket(t.reference)}
                              className="rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50 transition-colors"
                            >
                              Kapat
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {filteredTickets.length === 0 && !ticketsLoading && (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-sm text-slate-400">
                          Talep bulunamadı.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </SectionCard>
          )}

          {/* ══ DOCTORS ═══════════════════════════════════════════════════════ */}
          {activeTab === 'doctors' && (
            <div className="space-y-6">
              {/* Doctor form modal */}
              {doctorFormOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
                  <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
                    <h3 className="mb-4 text-base font-semibold text-slate-800">
                      {doctorEdit ? 'Doktoru Düzenle' : 'Yeni Doktor'}
                    </h3>
                    <form onSubmit={(e) => void onSaveDoctor(e)} className="space-y-3">
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">
                          Ad Soyad *
                        </label>
                        <input
                          required
                          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                          value={doctorFormName}
                          onChange={(e) => setDoctorFormName(e.target.value)}
                          placeholder="Dr. Ad Soyad"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">
                          Unvan
                        </label>
                        <input
                          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                          value={doctorFormTitle}
                          onChange={(e) => setDoctorFormTitle(e.target.value)}
                          placeholder="Uzm. Dr."
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">
                          Bölüm
                        </label>
                        <input
                          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                          value={doctorFormDeptName}
                          onChange={(e) => setDoctorFormDeptName(e.target.value)}
                          placeholder="Örn. Dahiliye"
                        />
                      </div>
                      {doctorFormMsg && <p className="text-sm text-red-600">{doctorFormMsg}</p>}
                      <div className="flex justify-end gap-2 pt-2">
                        <button
                          type="button"
                          onClick={() => setDoctorFormOpen(false)}
                          className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                        >
                          İptal
                        </button>
                        <button
                          type="submit"
                          className="rounded-lg bg-gradient-to-r from-sky-500 to-teal-500 px-5 py-2 text-sm font-semibold text-white hover:opacity-90"
                        >
                          Kaydet
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}

              {/* Blocked slots panel */}
              {blockedSlotDoctor && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
                  <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto">
                    <h3 className="mb-1 text-base font-semibold text-slate-800">
                      Randevu slotları — {blockedSlotDoctor.full_name}
                    </h3>
                    <p className="mb-3 text-xs text-slate-500">
                      Beyaz: müsait (tıklayınca kapanır). Kırmızı: yönetim tarafından kapatılmış
                      (tıklayınca açılır). Gri: hasta randevusu — değiştirilemez.
                    </p>
                    <div className="mb-4 flex flex-wrap items-center gap-2">
                      <label className="text-xs font-medium text-slate-600">Tarih</label>
                      <input
                        type="date"
                        className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
                        value={blockedSlotDay}
                        onChange={(e) => {
                          const v = e.target.value;
                          setBlockedSlotDay(v);
                          if (v) void loadDaySlots(blockedSlotDoctor.id, v);
                        }}
                      />
                    </div>
                    {daySlotsErr && <p className="mb-3 text-sm text-red-600">{daySlotsErr}</p>}
                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold text-slate-500 uppercase">
                            <th className="px-3 py-2">Saat</th>
                            <th className="px-3 py-2">Durum</th>
                          </tr>
                        </thead>
                        <tbody>
                          {daySlots.map((sl) => {
                            const bg =
                              sl.state === 'blocked'
                                ? 'bg-red-100 border-red-200'
                                : sl.state === 'booked'
                                  ? 'bg-slate-200 border-slate-300 cursor-not-allowed'
                                  : 'bg-white border-slate-200 hover:bg-sky-50 cursor-pointer';
                            return (
                              <tr key={sl.label} className="border-b border-slate-100">
                                <td className="px-3 py-2 font-medium text-slate-800 whitespace-nowrap">
                                  {sl.label}
                                </td>
                                <td className="p-2">
                                  <button
                                    type="button"
                                    disabled={sl.state === 'booked'}
                                    onClick={() => void onDaySlotCellClick(sl)}
                                    className={`w-full min-h-[40px] rounded-lg border text-left px-3 py-2 transition-colors ${bg} ${
                                      sl.state === 'booked' ? 'text-slate-600' : 'text-slate-800'
                                    }`}
                                  >
                                    {sl.state === 'free' && 'Müsait — kapatmak için tıklayın'}
                                    {sl.state === 'blocked' && 'Kapalı — açmak için tıklayın'}
                                    {sl.state === 'booked' && 'Randevu dolu'}
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    <div className="mt-4 flex justify-end">
                      <button
                        onClick={() => setBlockedSlotDoctor(null)}
                        className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                      >
                        Kapat
                      </button>
                    </div>
                  </div>
                </div>
              )}

              <SectionCard
                title={`Doktorlar (${doctors.length})`}
                action={
                  <div className="flex gap-2">
                    <button
                      onClick={openNewDoctorForm}
                      className="rounded-lg bg-gradient-to-r from-sky-500 to-teal-500 px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90"
                    >
                      + Yeni Doktor
                    </button>
                    <button
                      onClick={() => void loadDoctors()}
                      className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                    >
                      ↺ Yenile
                    </button>
                  </div>
                }
              >
                {doctorsLoading && (
                  <p className="py-4 text-center text-sm text-slate-400">Yükleniyor…</p>
                )}
                {doctorsErr && <p className="text-sm text-red-600 mb-3">{doctorsErr}</p>}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">
                        <th className="py-2 pr-4">Ad Soyad</th>
                        <th className="py-2 pr-4">Bölüm</th>
                        <th className="py-2 pr-4">Durum</th>
                        <th className="py-2">İşlem</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {doctors.map((doc) => (
                        <tr key={doc.id} className="hover:bg-slate-50/60 transition-colors">
                          <td className="py-3 pr-4">
                            <p className="font-medium text-slate-800">{doc.full_name}</p>
                            {doc.title && <p className="text-xs text-slate-400">{doc.title}</p>}
                          </td>
                          <td className="py-3 pr-4 text-slate-600">
                            {doc.department_name ?? <span className="text-slate-300">—</span>}
                          </td>
                          <td className="py-3 pr-4">
                            <span
                              className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                                doc.is_active
                                  ? 'bg-emerald-100 text-emerald-700'
                                  : 'bg-slate-100 text-slate-500'
                              }`}
                            >
                              {doc.is_active ? 'Aktif' : 'Pasif'}
                            </span>
                          </td>
                          <td className="py-3">
                            <div className="flex gap-1.5">
                              <button
                                onClick={() => openEditDoctorForm(doc)}
                                className="rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                              >
                                Düzenle
                              </button>
                              <button
                                onClick={() => void onOpenBlockedSlots(doc)}
                                className="rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                              >
                                Slotlar
                              </button>
                              <button
                                onClick={() => void onToggleDoctorActive(doc)}
                                className={`rounded border px-2 py-1 text-xs ${
                                  doc.is_active
                                    ? 'border-rose-200 text-rose-600 hover:bg-rose-50'
                                    : 'border-emerald-200 text-emerald-600 hover:bg-emerald-50'
                                }`}
                              >
                                {doc.is_active ? 'Pasifleştir' : 'Aktifleştir'}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                      {doctors.length === 0 && !doctorsLoading && (
                        <tr>
                          <td colSpan={4} className="py-8 text-center text-sm text-slate-400">
                            Henüz doktor eklenmemiş.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </SectionCard>
            </div>
          )}

          {/* ══ LLM SETTINGS ══════════════════════════════════════════════════ */}
          {activeTab === 'llm' && canTenantAdmin(role) && (
            <div className="space-y-6">
              <SectionCard title="RAG Politikası">
                {policyErr && <p className="mb-3 text-sm text-red-700">{policyErr}</p>}
                {tenantPolicy && (
                  <label className="flex cursor-pointer items-center gap-3 text-sm text-slate-800">
                    <input
                      type="checkbox"
                      checked={tenantPolicy.rag_retrieval_enabled}
                      onChange={(e) => void onToggleRagPolicy(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-sky-500 focus:ring-sky-400"
                    />
                    <span>
                      RAG retrieval açık —{' '}
                      <code className="rounded bg-slate-100 px-1 text-xs">/documents/retrieve</code>{' '}
                      aktif
                    </span>
                  </label>
                )}
                {policyMsg && <p className="mt-2 text-sm text-green-700">{policyMsg}</p>}
              </SectionCard>

              <SectionCard title="Agent LLM Ayarları">
                <p className="mb-4 text-sm text-slate-500">
                  Boş bırakılan alanlar değiştirilmez. Yalnızca doldurulan alanlar güncellenir.
                </p>
                {agentLlmErr && <p className="mb-3 text-sm text-red-700">{agentLlmErr}</p>}
                <form onSubmit={(e) => void onSaveAgentLlm(e)} className="max-w-lg space-y-4">
                  {[
                    {
                      label: 'LLM Modeli',
                      value: agentLlmModel,
                      set: setAgentLlmModel,
                      ph: 'gpt-4o-mini',
                      mono: true,
                    },
                    {
                      label: 'Sıcaklık (0–2)',
                      value: agentLlmTemp,
                      set: setAgentLlmTemp,
                      ph: '0.25',
                    },
                    {
                      label: 'Maks. geçmiş uzunluğu',
                      value: agentLlmHist,
                      set: setAgentLlmHist,
                      ph: '20',
                    },
                  ].map((f) => (
                    <label key={f.label} className="block text-sm font-medium text-slate-700">
                      {f.label}
                      <input
                        className={`mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500 ${f.mono ? 'font-mono text-sm' : ''}`}
                        value={f.value}
                        onChange={(e) => f.set(e.target.value)}
                        placeholder={f.ph}
                      />
                    </label>
                  ))}
                  {agentLlmMsg && <p className="text-sm text-green-700">{agentLlmMsg}</p>}
                  <button
                    type="submit"
                    className="rounded-lg bg-gradient-to-r from-sky-500 to-teal-500 px-5 py-2 text-sm font-semibold text-white hover:opacity-90"
                  >
                    Kaydet
                  </button>
                </form>
              </SectionCard>
            </div>
          )}

          {/* ══ RAG / DOCUMENTS ═══════════════════════════════════════════════ */}
          {activeTab === 'rag' && (
            <div className="space-y-6">
              {editDoc && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
                  <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
                    <h3 className="mb-1 text-base font-semibold text-slate-800">
                      Dokümanı düzenle
                    </h3>
                    <p className="mb-4 text-xs text-slate-500">
                      Kaydettiğinizde metin yeniden parçalanır ve Chroma vektörleri güncellenir.
                    </p>
                    {editDocLoading && <p className="mb-3 text-sm text-slate-400">Yükleniyor…</p>}
                    <form onSubmit={(e) => void onSaveEditDocument(e)} className="space-y-3">
                      <label className="block text-sm font-medium text-slate-700">
                        Başlık
                        <input
                          required
                          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-sky-500 focus:outline-none"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          maxLength={512}
                        />
                      </label>
                      <label className="block text-sm font-medium text-slate-700">
                        İçerik
                        <textarea
                          required
                          rows={14}
                          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm text-slate-900 focus:border-sky-500 focus:outline-none"
                          value={editContent}
                          onChange={(e) => setEditContent(e.target.value)}
                        />
                      </label>
                      {editDocErr && <p className="text-sm text-red-600">{editDocErr}</p>}
                      <div className="flex justify-end gap-2 pt-2">
                        <button
                          type="button"
                          onClick={() => {
                            setEditDoc(null);
                            setEditDocErr(null);
                          }}
                          className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                        >
                          İptal
                        </button>
                        <button
                          type="submit"
                          disabled={editDocLoading}
                          className="rounded-lg bg-gradient-to-r from-sky-500 to-teal-500 px-5 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
                        >
                          Kaydet
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}

              <SectionCard
                title={`Dokümanlar (${docs.length})`}
                action={
                  <button
                    onClick={() => void loadDocs()}
                    className="text-xs text-sky-600 hover:underline"
                  >
                    ↺ Yenile
                  </button>
                }
              >
                {docsErr && <p className="mb-3 text-sm text-red-700">{docsErr}</p>}
                {reindexHint && <p className="mb-3 text-sm text-sky-700">{reindexHint}</p>}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">
                        <th className="py-2 pr-4">Başlık</th>
                        <th className="py-2 pr-4">Kaynak</th>
                        <th className="py-2 pr-4">Durum</th>
                        <th className="py-2 pr-4">Parça</th>
                        <th className="py-2 pr-4">Tarih</th>
                        <th className="py-2">İşlem</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {docs.map((d) => (
                        <tr key={d.id} className="hover:bg-slate-50/60">
                          <td className="py-3 pr-4 font-medium text-slate-800">{d.title}</td>
                          <td className="py-3 pr-4 text-slate-500">{d.source_type}</td>
                          <td className="py-3 pr-4">
                            <StatusBadge status={d.status} />
                          </td>
                          <td className="py-3 pr-4 text-slate-600">{d.chunk_count}</td>
                          <td className="py-3 pr-4 text-xs text-slate-400">
                            {new Date(d.created_at).toLocaleDateString('tr-TR')}
                          </td>
                          <td className="py-3">
                            {canManageDocuments(role) && (
                              <div className="flex flex-wrap gap-1.5">
                                {d.status === 'completed' && (
                                  <button
                                    type="button"
                                    onClick={() => void onReindexEmbeddings(d.id)}
                                    className="rounded border border-sky-200 px-2 py-1 text-xs text-sky-700 hover:bg-sky-50"
                                  >
                                    Reindex
                                  </button>
                                )}
                                {d.status !== 'processing' && d.status !== 'pending' && (
                                  <button
                                    type="button"
                                    onClick={() => void openEditDocument(d.id)}
                                    className="rounded border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                                  >
                                    Düzenle
                                  </button>
                                )}
                                <button
                                  onClick={() => void onDelete(d.id)}
                                  className="rounded border border-red-200 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                                >
                                  Sil
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                      {docs.length === 0 && (
                        <tr>
                          <td colSpan={6} className="py-8 text-center text-sm text-slate-400">
                            Doküman yok.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </SectionCard>

              {canManageDocuments(role) && (
                <SectionCard title="Yeni Doküman Yükle">
                  <form onSubmit={onIngest} className="max-w-lg space-y-4">
                    {[
                      {
                        label: 'Başlık',
                        value: ingestTitle,
                        set: setIngestTitle,
                        type: 'text',
                        max: 512,
                      },
                      {
                        label: 'Kaynak tipi',
                        value: ingestSource,
                        set: setIngestSource,
                        type: 'text',
                        max: 64,
                      },
                    ].map((f) => (
                      <label key={f.label} className="block text-sm font-medium text-slate-700">
                        {f.label}
                        <input
                          required={f.label === 'Başlık'}
                          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-sky-500 focus:outline-none"
                          value={f.value}
                          onChange={(e) => f.set(e.target.value)}
                          maxLength={f.max}
                        />
                      </label>
                    ))}
                    <label className="block text-sm font-medium text-slate-700">
                      İçerik (hastane kitapçığı, kurallar, bilgi)
                      <textarea
                        required
                        className="mt-1 min-h-[160px] w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-sky-500 focus:outline-none"
                        value={ingestContent}
                        onChange={(e) => setIngestContent(e.target.value)}
                      />
                    </label>
                    {ingestMsg && <p className="text-sm text-green-700">{ingestMsg}</p>}
                    <button
                      type="submit"
                      className="rounded-lg bg-gradient-to-r from-sky-500 to-teal-500 px-5 py-2 text-sm font-semibold text-white hover:opacity-90"
                    >
                      Yükle
                    </button>
                  </form>
                </SectionCard>
              )}
            </div>
          )}

          {/* ══ SETTINGS ══════════════════════════════════════════════════════ */}
          {activeTab === 'settings' && (
            <div className="space-y-6">
              {canTenantAdmin(role) && (
                <SectionCard title="Hastane Adı">
                  <p className="mb-4 text-sm text-slate-500">
                    Bu isim admin panelinde, chat sayfasında ve tüm arayüzlerde görünür.
                  </p>
                  <form onSubmit={(e) => void onSaveHospitalName(e)} className="max-w-sm space-y-3">
                    <label className="block text-sm font-medium text-slate-700">
                      Hastane Adı
                      <input
                        required
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                        value={hospitalNameInput}
                        onChange={(e) => setHospitalNameInput(e.target.value)}
                        placeholder="XYZ Hastanesi"
                        maxLength={255}
                      />
                    </label>
                    {hospitalNameMsg && (
                      <p
                        className={`text-sm ${hospitalNameMsg.includes('güncellendi') ? 'text-green-700' : 'text-red-600'}`}
                      >
                        {hospitalNameMsg}
                      </p>
                    )}
                    <button
                      type="submit"
                      className="rounded-lg bg-gradient-to-r from-sky-500 to-teal-500 px-5 py-2 text-sm font-semibold text-white hover:opacity-90"
                    >
                      Kaydet
                    </button>
                  </form>
                </SectionCard>
              )}

              {canTenantAdmin(role) && (
                <SectionCard
                  title="Kullanıcılar"
                  action={
                    <button
                      onClick={() => void loadAdminUsers()}
                      className="text-xs text-sky-600 hover:underline"
                    >
                      ↺ Yenile
                    </button>
                  }
                >
                  {adminUsersErr && <p className="mb-3 text-sm text-red-700">{adminUsersErr}</p>}
                  {userAdminMsg && <p className="mb-3 text-sm text-green-700">{userAdminMsg}</p>}
                  <ul className="divide-y divide-slate-100">
                    {adminUsers.map((u) => (
                      <li
                        key={u.id}
                        className="flex flex-wrap items-center justify-between gap-3 py-3"
                      >
                        <div>
                          <p className="font-medium text-slate-900">{u.email}</p>
                          <p className="text-xs text-slate-500">
                            {u.full_name ?? '—'} ·{' '}
                            <span className="font-medium text-sky-700">admin</span>
                            {' · '}
                            {u.is_active ? 'aktif' : 'pasif'}
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <button
                            disabled={u.id === me.id}
                            className="rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                            onClick={() => void onPatchUser(u.id, { is_active: !u.is_active })}
                          >
                            {u.is_active ? 'Pasifleştir' : 'Aktifleştir'}
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                </SectionCard>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
