# HospitAI — dağıtım notları

Bu dosya üretim öncesi kontrol listesi ve tipik mimariyi özetler. Ayrıntılı env alanları için `backend/.env.example`, `infra/env.example` ve `infra/README.md` dosyalarına bakın.

## Bileşenler

| Bileşen               | Açıklama                                                                              |
| --------------------- | ------------------------------------------------------------------------------------- |
| **PostgreSQL**        | Uygulama verisi, Alembic migrasyonları (`backend/alembic`).                           |
| **Redis**             | Celery broker (embedding reindex, domain event kuyruğu).                              |
| **Chroma**            | Vektör depolama (`CHROMA_HOST` / `CHROMA_PORT`).                                      |
| **Backend (FastAPI)** | `uvicorn hospitai.api.main:app`, `DATABASE_URL` async (`+asyncpg`).                   |
| **Celery worker**     | `celery -A hospitai.workers.celery_app worker` — Redis ve DB erişimi gerekir.         |
| **Agent**             | `hospitai-agent` paketi backend ile aynı ortamda kurulur (`pip install -e ../agent`). |

## Dağıtım sırası (öneri)

1. Postgres ve Redis’i ayağa kaldırın; gerekirse Chroma’yı ayrı servis olarak çalıştırın.
2. `backend/.env` içinde güçlü `JWT_SECRET`, üretim `DATABASE_URL`, LLM/embedding API anahtarlarını tanımlayın.
3. `alembic upgrade head` (backend dizininde).
4. API sürecini başlatın; ardından en az bir Celery worker örneği başlatın (reindex ve `ticket.created` bildirim kuyruğu için).
5. `frontend` ve `frontend-admin` için `npm run build` çıktısını statik dosya sunucusu veya CDN arkasına koyun; API ile aynı kökteğe reverse proxy (`/api` → backend) kullanın.

## Reverse proxy

- TLS sonlandırma, `X-Forwarded-For` ve `X-Request-ID` iletimi önerilir.
- Rate limit IP başına çalışır; proxy arkasında doğru istemci IP’si için `Forwarded` / `X-Forwarded-For` güvenilen hop sayısını yapılandırın (ileride uygulama tarafında genişletilebilir).

## Sağlık kontrolleri

- `GET /healthz`, `GET /readyz` — yük dengeleyici ve orchestrator health check’leri için kullanılabilir.

## CI

GitHub Actions (`.github/workflows/ci.yml`) backend lint/test ve frontend build doğrular. Üretim dağıtımı bu pipeline’a bağlanabilir.
