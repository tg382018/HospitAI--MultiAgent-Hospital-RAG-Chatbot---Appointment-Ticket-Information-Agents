import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { streamChat } from './lib/api';

/* ─── Types ─────────────────────────────────────────────────────────────── */
type Role = 'user' | 'assistant';
interface ChatMsg {
  id: string;
  role: Role;
  content: string;
  ts: Date;
}

/* ─── Constants ─────────────────────────────────────────────────────────── */
const SS_CONV = 'hospitai-chat-conversation-id';

const QUICK_CHIPS = [
  { icon: '📅', label: 'Randevu Al' },
  { icon: '📋', label: 'Randevularım' },
  { icon: '💬', label: 'Şikayet Bildir' },
  { icon: '❓', label: 'Hastane Bilgisi' },
];

const WELCOME_TITLE = 'Merhaba! 👋';
const WELCOME_SUB =
  'Size nasıl yardımcı olabilirim? Randevu almak, randevularınızı sorgulamak veya bir şikayetinizi iletmek için aşağıdan başlayabilirsiniz.';

/* ─── Helpers ────────────────────────────────────────────────────────────── */
function uid() {
  return Math.random().toString(36).slice(2);
}

function fmtTime(d: Date) {
  return d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
}

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

/* ─── Sub-components ─────────────────────────────────────────────────────── */

function TypingIndicator() {
  return (
    <div className="msg-assistant flex items-end gap-2 max-w-[80%]">
      <div className="flex-shrink-0 w-8 h-8 rounded-full overflow-hidden shadow-sm border-2 border-white">
        <img src="/ai-doctor-avatar.png" alt="AI" className="w-full h-full object-cover" />
      </div>
      <div className="rounded-2xl rounded-bl-sm bg-white shadow-sm border border-slate-100 px-4 py-3">
        <div className="flex items-center gap-1.5">
          <div className="typing-dot w-2 h-2 rounded-full bg-sky-400" />
          <div className="typing-dot w-2 h-2 rounded-full bg-sky-400" />
          <div className="typing-dot w-2 h-2 rounded-full bg-sky-400" />
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === 'user';
  return (
    <div
      className={`flex items-end gap-2 ${isUser ? 'flex-row-reverse msg-user' : 'msg-assistant'}`}
    >
      {/* Avatar */}
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full overflow-hidden shadow-sm border-2 border-white">
          <img src="/ai-doctor-avatar.png" alt="AI" className="w-full h-full object-cover" />
        </div>
      )}
      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-sky-400 to-teal-500 flex items-center justify-center shadow-sm">
          <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" />
          </svg>
        </div>
      )}

      <div className={`flex flex-col gap-1 max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`
            px-4 py-3 text-sm leading-relaxed shadow-sm whitespace-pre-wrap
            ${
              isUser
                ? 'bg-gradient-to-br from-sky-500 to-teal-500 text-white rounded-2xl rounded-br-sm'
                : 'bg-white text-slate-700 rounded-2xl rounded-bl-sm border border-slate-100'
            }
          `}
        >
          {msg.content || <span className="text-sky-200 italic text-xs">…</span>}
        </div>
        <span className="text-[10px] text-slate-400 px-1">{fmtTime(msg.ts)}</span>
      </div>
    </div>
  );
}

function QuickChips({ onPick }: { onPick: (label: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2 justify-center px-2">
      {QUICK_CHIPS.map((c, i) => (
        <button
          key={c.label}
          onClick={() => onPick(c.label)}
          className="chip-enter flex items-center gap-1.5 rounded-full border border-sky-200 bg-white px-4 py-2 text-sm font-medium text-sky-700 shadow-sm transition-all hover:bg-sky-50 hover:border-sky-400 hover:scale-105 active:scale-95"
          style={{ animationDelay: `${i * 0.07}s` }}
        >
          <span>{c.icon}</span>
          {c.label}
        </button>
      ))}
    </div>
  );
}

/* ─── Main component ─────────────────────────────────────────────────────── */
export function ChatApp() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [draft, setDraft] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [chatErr, setChatErr] = useState('');
  const [sending, setSending] = useState(false);
  const [isTyping, setIsTyping] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const chatAreaRef = useRef<HTMLDivElement>(null);

  /* Load stored conversation id */
  useEffect(() => {
    const cid = sessionStorage.getItem(SS_CONV);
    if (cid) setConversationId(cid);
  }, []);

  /* Auto-scroll to bottom on new messages */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  /* Handle Enter key (Shift+Enter = newline) */
  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!sending && draft.trim()) {
        void handleSend(draft.trim());
      }
    }
  };

  const handleSend = useCallback(
    async (text: string) => {
      if (!text.trim() || sending) return;
      setChatErr('');
      setSending(true);
      setDraft('');
      setIsTyping(true);

      const userMsg: ChatMsg = { id: uid(), role: 'user', content: text, ts: new Date() };
      setMessages((m) => [...m, userMsg]);

      const assistantId = uid();
      let acc = '';

      try {
        const body: Record<string, unknown> = { message: text };
        if (conversationId) body.conversation_id = conversationId;

        await streamChat(
          '/api/v1/chat/stream',
          { method: 'POST', headers: {}, json: body },
          {
            onMeta: (d) => {
              setConversationId(d.conversation_id);
              sessionStorage.setItem(SS_CONV, d.conversation_id);
            },
            onToken: (t) => {
              acc += t;
              setIsTyping(false);
              setMessages((m) => {
                const existing = m.find((x) => x.id === assistantId);
                if (existing) {
                  return m.map((x) => (x.id === assistantId ? { ...x, content: acc } : x));
                }
                return [...m, { id: assistantId, role: 'assistant', content: acc, ts: new Date() }];
              });
            },
            onFinal: (d) => {
              setIsTyping(false);
              let finalMsg = d.message;
              if (d.escalated) finalMsg = `⚠️ Acil yönlendirme\n\n${finalMsg}`;
              else if (d.safety_flag) finalMsg = `⚠️ Güvenlik uyarısı\n\n${finalMsg}`;
              setMessages((m) => {
                const existing = m.find((x) => x.id === assistantId);
                if (existing) {
                  return m.map((x) => (x.id === assistantId ? { ...x, content: finalMsg } : x));
                }
                return [
                  ...m,
                  { id: assistantId, role: 'assistant', content: finalMsg, ts: new Date() },
                ];
              });
            },
            onError: (msg) => {
              throw new Error(msg);
            },
          }
        );
      } catch (e) {
        setIsTyping(false);
        setChatErr(formatErr(e));
        setMessages((m) => m.filter((x) => x.id !== assistantId));
      } finally {
        setSending(false);
        setIsTyping(false);
        setTimeout(() => inputRef.current?.focus(), 50);
      }
    },
    [conversationId, sending]
  );

  const onSubmit = (ev: FormEvent) => {
    ev.preventDefault();
    void handleSend(draft.trim());
  };

  const onChipClick = (label: string) => {
    void handleSend(label);
  };

  const onClearChat = () => {
    setMessages([]);
    setConversationId(null);
    sessionStorage.removeItem(SS_CONV);
    setChatErr('');
  };

  const showEmpty = messages.length === 0 && !sending;

  return (
    <div className="flex min-h-dvh flex-col">
      {/* ── Hero Header ─────────────────────────────────────────── */}
      <div
        className="relative overflow-hidden"
        style={{
          background: 'linear-gradient(135deg, #0ea5e9 0%, #0891b2 50%, #14b8a6 100%)',
        }}
      >
        {/* Background illustration */}
        <div
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage: 'url(/hospital-hero.png)',
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            mixBlendMode: 'luminosity',
          }}
        />

        {/* Decorative circles */}
        <div className="absolute -top-8 -right-8 w-48 h-48 rounded-full bg-white/10 blur-2xl" />
        <div className="absolute -bottom-12 -left-12 w-56 h-56 rounded-full bg-teal-300/20 blur-3xl" />

        <div className="relative mx-auto max-w-2xl px-4 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl overflow-hidden shadow-lg border-2 border-white/30 float-slow">
              <img
                src="/ai-doctor-avatar.png"
                alt="HospitAI"
                className="w-full h-full object-cover"
              />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">HospitAI</h1>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="pulse-green w-2 h-2 rounded-full bg-green-400 inline-block" />
                <span className="text-xs text-sky-100 font-medium">Çevrimiçi · 7/24 Aktif</span>
              </div>
            </div>
          </div>

          <button
            onClick={onClearChat}
            title="Yeni konuşma başlat"
            className="rounded-xl bg-white/15 px-3 py-2 text-xs font-medium text-white hover:bg-white/25 transition-all active:scale-95 flex items-center gap-1.5"
          >
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            Yeni
          </button>
        </div>

        {/* Bottom fade */}
        <div
          className="absolute bottom-0 left-0 right-0 h-4"
          style={{ background: 'linear-gradient(to bottom, transparent, rgba(240,253,250,0.4))' }}
        />
      </div>

      {/* ── Chat Area ───────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col mx-auto w-full max-w-2xl px-4">
        <div
          ref={chatAreaRef}
          className="flex-1 overflow-y-auto py-5 flex flex-col gap-4"
          style={{ minHeight: 'calc(100dvh - 220px)', maxHeight: 'calc(100dvh - 220px)' }}
        >
          {/* Empty / welcome state */}
          {showEmpty && (
            <div className="flex flex-col items-center justify-center flex-1 gap-6 py-8 msg-fade">
              <div className="relative">
                <div className="w-24 h-24 rounded-3xl overflow-hidden shadow-xl border-4 border-white float-slow">
                  <img
                    src="/ai-doctor-avatar.png"
                    alt="HospitAI"
                    className="w-full h-full object-cover"
                  />
                </div>
                <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-green-400 border-2 border-white pulse-green" />
              </div>
              <div className="text-center max-w-xs">
                <h2 className="text-xl font-bold text-slate-800">{WELCOME_TITLE}</h2>
                <p className="mt-2 text-sm text-slate-500 leading-relaxed">{WELCOME_SUB}</p>
              </div>
              <QuickChips onPick={onChipClick} />
            </div>
          )}

          {/* Messages */}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}

          {/* Typing indicator */}
          {isTyping && <TypingIndicator />}

          {/* Auto-scroll anchor */}
          <div ref={bottomRef} />
        </div>

        {/* Error banner */}
        {chatErr && (
          <div className="mx-1 mb-2 flex items-center gap-2 rounded-xl bg-rose-50 border border-rose-200 px-4 py-2.5 text-sm text-rose-600 msg-fade">
            <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            {chatErr}
          </div>
        )}

        {/* ── Input bar ───────────────────────────────────────────── */}
        <div className="pb-4 pt-1">
          <form
            onSubmit={onSubmit}
            className="flex items-end gap-2 rounded-2xl bg-white shadow-lg border border-slate-100 p-2"
          >
            <textarea
              ref={inputRef}
              rows={1}
              className="min-w-0 flex-1 resize-none bg-transparent px-2 py-2 text-sm text-slate-700 placeholder:text-slate-400 outline-none leading-relaxed"
              style={{ maxHeight: '120px', overflowY: 'auto' }}
              placeholder="Mesajınızı yazın… (Enter = gönder, Shift+Enter = yeni satır)"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                // auto-height
                e.target.style.height = 'auto';
                e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
              }}
              onKeyDown={onKeyDown}
              disabled={sending}
            />
            <button
              type="submit"
              disabled={sending || !draft.trim()}
              className={`
                flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all
                ${
                  !draft.trim() || sending
                    ? 'bg-slate-100 text-slate-300 cursor-not-allowed'
                    : 'bg-gradient-to-br from-sky-500 to-teal-500 text-white shadow-md hover:shadow-lg hover:scale-105 active:scale-95'
                }
              `}
            >
              {sending ? (
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              ) : (
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2.5}
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
                  />
                </svg>
              )}
            </button>
          </form>
          <p className="mt-2 text-center text-[10px] text-slate-400">
            HospitAI · Yapay zeka tarafından üretilir · Acil durumlarda 112'yi arayın
          </p>
        </div>
      </div>
    </div>
  );
}
