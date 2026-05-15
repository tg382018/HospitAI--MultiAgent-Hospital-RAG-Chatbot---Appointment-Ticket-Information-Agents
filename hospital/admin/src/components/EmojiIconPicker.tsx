import { useEffect, useId, useRef, useState } from 'react';

const EMOJI_CATEGORIES: { id: string; label: string; emojis: string[] }[] = [
  {
    id: 'hospital',
    label: 'Sağlık',
    emojis: [
      '📅',
      '📋',
      '💬',
      '❓',
      '🏥',
      '⚕️',
      '🩺',
      '💊',
      '🧑‍⚕️',
      '🚑',
      '🩹',
      '❤️‍🩹',
      '🦷',
      '👁️',
      '🧠',
      '🫀',
    ],
  },
  {
    id: 'actions',
    label: 'İşlem',
    emojis: [
      '✅',
      '❌',
      '⚠️',
      'ℹ️',
      '🔔',
      '📞',
      '📧',
      '📍',
      '🔍',
      '➕',
      '✏️',
      '🗑️',
      '⏰',
      '📆',
      '🔗',
      '⭐',
    ],
  },
  {
    id: 'faces',
    label: 'Yüz',
    emojis: ['👋', '🙂', '😊', '🤝', '🙏', '💪', '🎉', '👍', '👎', '😢', '😮', '🤔'],
  },
  {
    id: 'custom',
    label: 'Özel',
    emojis: [],
  },
];

type EmojiIconPickerProps = {
  value: string;
  onChange: (icon: string) => void;
};

export function EmojiIconPicker({ value, onChange }: EmojiIconPickerProps) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState(EMOJI_CATEGORIES[0].id);
  const [custom, setCustom] = useState(value);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    setCustom(value);
  }, [value]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const active = EMOJI_CATEGORIES.find((c) => c.id === tab) ?? EMOJI_CATEGORIES[0];

  function pick(emoji: string) {
    onChange(emoji);
    setCustom(emoji);
    setOpen(false);
  }

  function applyCustom() {
    const trimmed = custom.trim().slice(0, 8);
    if (!trimmed) return;
    onChange(trimmed);
    setOpen(false);
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="mt-1 flex h-11 w-16 items-center justify-center rounded-lg border border-slate-300 bg-white text-2xl shadow-sm transition-colors hover:border-sky-400 hover:bg-sky-50 focus:outline-none focus:ring-2 focus:ring-sky-500"
        title="İkon seç"
      >
        {value.trim() || <span className="text-base text-slate-400">＋</span>}
      </button>

      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-label="İkon seçici"
          className="absolute left-0 top-full z-50 mt-2 w-[min(100vw-2rem,20rem)] rounded-xl border border-slate-200 bg-white p-3 shadow-xl"
        >
          <div className="mb-2 flex gap-1 overflow-x-auto border-b border-slate-100 pb-2">
            {EMOJI_CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                type="button"
                onClick={() => setTab(cat.id)}
                className={`shrink-0 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  tab === cat.id ? 'bg-sky-500 text-white' : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>

          {tab === 'custom' ? (
            <div className="space-y-2">
              <p className="text-xs text-slate-500">
                Emoji veya kısa simge yapıştırın (en fazla 8 karakter).
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  maxLength={8}
                  value={custom}
                  onChange={(e) => setCustom(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') applyCustom();
                  }}
                  className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-center text-lg"
                  placeholder="📅"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={applyCustom}
                  className="rounded-lg bg-sky-500 px-3 py-2 text-sm font-medium text-white hover:bg-sky-600"
                >
                  Uygula
                </button>
              </div>
            </div>
          ) : (
            <div className="grid max-h-40 grid-cols-8 gap-1 overflow-y-auto">
              {active.emojis.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  onClick={() => pick(emoji)}
                  className={`flex h-9 w-9 items-center justify-center rounded-lg text-xl transition-colors hover:bg-sky-50 ${
                    value === emoji ? 'bg-sky-100 ring-2 ring-sky-400' : ''
                  }`}
                  title={emoji}
                >
                  {emoji}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
