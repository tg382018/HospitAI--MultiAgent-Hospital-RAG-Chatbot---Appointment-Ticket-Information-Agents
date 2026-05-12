# HospitAI

Hospital AI Agent Platform — monorepo (`frontend`, `backend`, `infra`).

## Kurulum

```bash
npm install
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
```

## Komutlar

| Komut                     | Açıklama                          |
| ------------------------- | --------------------------------- |
| `npm run format`          | Prettier (JS/TS/CSS/JSON/YAML/MD) |
| `npm run lint`            | Frontend ESLint                   |
| `npm run dev -w frontend` | Vite geliştirme sunucusu          |

Backend: `cd backend && ruff check src tests && ruff format src tests`

## Yerel referans dosyaları

Ürün özeti ve yol haritası için kökteki `project.txt` ve `PLAN.md` kullanılır; bu dosyalar `.gitignore` ile depoya alınmaz. Ekibin her üyesi kendi kopyasını tutmalıdır.

## Husky

Commit öncesi `lint-staged` Prettier çalıştırır (TS/JS/CSS/JSON/YAML/MD).
