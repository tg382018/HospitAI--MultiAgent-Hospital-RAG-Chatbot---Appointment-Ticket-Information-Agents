# HospitAI

Hospital AI Agent Platform — monorepo (`frontend`, `backend`, **`agent/`** (hedef LangGraph paketi), `infra`). Yol haritası: [PLAN.md](PLAN.md).

## Docker (yerel veri katmanı)

Postgres, Redis, Chroma ve isteğe bağlı **XYZ Hospital** referans API’si:

```bash
npm run docker:up
```

İlk çalıştırmada `xyz-hospital` imajı derlenir; sadece veri katmanı isteniyorsa Compose dosyasında bu servisi yorum satırı yapabilirsiniz.

İsteğe bağlı: `cp infra/env.example infra/.env` ile portları ve şifreleri özelleştir. Ayrıntılar için [infra/README.md](infra/README.md).

## Kurulum

```bash
npm install
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ../agent
pip install -e ".[dev]"
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

`hospitai-agent`, LangGraph paketidir; backend ona çalışma zamanında bağlıdır.

## Komutlar

| Komut                     | Açıklama                                             |
| ------------------------- | ---------------------------------------------------- |
| `npm run docker:up`       | Postgres + Redis + Chroma (+ **xyz-hospital** imajı) |
| `npm run docker:down`     | Compose stack’i durdurur                             |
| `npm run docker:ps`       | Servis durumu                                        |
| `npm run docker:logs`     | Tüm servislerin logları (follow)                     |
| `npm run format`          | Prettier (JS/TS/CSS/JSON/YAML/MD)                    |
| `npm run lint`            | Frontend ESLint                                      |
| `npm run dev -w frontend` | Vite geliştirme sunucusu                             |

Backend migrasyonları: `cd backend && alembic upgrade head` (önce `npm run docker:up` ve `backend/.env`).

API sunucusu: `cd backend && uvicorn hospitai.api.main:app --reload --port 8000` (Vite proxy `/api` ve `/ws` için 8000).

Backend kalite: `cd backend && ruff check src tests alembic && ruff format src tests alembic && pytest`

## Ürün özeti

Uzun prompt için isteğe bağlı yerel `project.txt` (`.gitignore` ile hariç tutulabilir). **Yol haritası ve mimari:** repodaki [PLAN.md](PLAN.md). **Agent kodunun hedef klasörü:** [agent/README.md](agent/README.md).

## Husky

Commit öncesi `lint-staged` Prettier çalıştırır (TS/JS/CSS/JSON/YAML/MD).
