# HospitAI

Hospital AI Agent Platform — monorepo (`frontend`, `backend`, `infra`).

## Docker (yerel veri katmanı)

Postgres, Redis ve Chroma:

```bash
npm run docker:up
```

İsteğe bağlı: `cp infra/env.example infra/.env` ile portları ve şifreleri özelleştir. Ayrıntılar için [infra/README.md](infra/README.md).

## Kurulum

```bash
npm install
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

## Komutlar

| Komut                     | Açıklama                             |
| ------------------------- | ------------------------------------ |
| `npm run docker:up`       | Postgres + Redis + Chroma (detached) |
| `npm run docker:down`     | Compose stack’i durdurur             |
| `npm run docker:ps`       | Servis durumu                        |
| `npm run docker:logs`     | Tüm servislerin logları (follow)     |
| `npm run format`          | Prettier (JS/TS/CSS/JSON/YAML/MD)    |
| `npm run lint`            | Frontend ESLint                      |
| `npm run dev -w frontend` | Vite geliştirme sunucusu             |

Backend: `cd backend && ruff check src tests && ruff format src tests`

## Yerel referans dosyaları

Ürün özeti ve yol haritası için kökteki `project.txt` ve `PLAN.md` kullanılır; bu dosyalar `.gitignore` ile depoya alınmaz. Ekibin her üyesi kendi kopyasını tutmalıdır.

## Husky

Commit öncesi `lint-staged` Prettier çalıştırır (TS/JS/CSS/JSON/YAML/MD).
