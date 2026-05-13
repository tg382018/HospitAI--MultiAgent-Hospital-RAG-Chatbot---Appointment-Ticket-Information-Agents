# HospitAI Backend

Python / FastAPI servisi. Katmanlar:

- `domain/` — kurallar ve modeller (framework bağımsız)
- `application/` — use case’ler ve port arayüzleri
- `infrastructure/` — DB, cache, dış servis implementasyonları
- `api/` — HTTP/WebSocket sunumu

## HTTP API (FastAPI)

- **Giriş**: `hospitai.api.main:app` (`create_app()` fabrika).
- **Yol örnekleri**: `GET /healthz`, `GET /readyz`, `GET /api/v1/ping`, `POST /api/v1/auth/login`, `GET /api/v1/users/me`, `GET /api/v1/appointments/available-slots`, `POST /api/v1/tickets`, …
- **OpenAPI**: `ENVIRONMENT!=production` iken `/docs`, `/redoc`, `/openapi.json`.
- **Ortam**: `backend/.env` (kök `backend/` klasörüne göre mutlak yol ile okunur; monorepo kökünden çalıştırsan da bulunur).
- **Log**: `structlog` — geliştirmede renkli konsol, diğer ortamlarda JSON.
- **Hata gövdesi**: `{"error": {"code", "message", "request_id"}}` + `X-Request-ID` middleware.

### Kimlik doğrulama (JWT)

- **Login**: `POST /api/v1/auth/login` — gövde: `tenant_slug`, `email`, `password`.
- **Kayıt** (açıksa): `POST /api/v1/auth/register` — yalnızca **patient** rolü; `ALLOW_OPEN_REGISTRATION=false` ile kapatılır.
- **Refresh**: `POST /api/v1/auth/refresh` — `refresh_token`.
- **Profil**: `GET /api/v1/users/me` — `Authorization: Bearer <access>`.
- **RBAC örneği**: `GET /api/v1/admin/ping` — yalnızca `admin`.
- **İç servis**: `GET /api/v1/internal/ping` — `INTERNAL_API_KEY` tanımlıysa `X-Internal-Key` zorunlu.

### Randevu ve ticket (domain API)

Bearer JWT zorunlu; tenant bağlamı kullanıcıdan gelir.

| Metot                               | Açıklama                                                              |
| ----------------------------------- | --------------------------------------------------------------------- |
| `GET /appointments/available-slots` | `doctor_id`, `day`, isteğe bağlı `slot_minutes` — 09:00–17:00 **UTC** |
| `GET /appointments`                 | Hasta: kendi listesi; personel rolleri: tenant geneli                 |
| `POST /appointments`                | Oluştur; `patient_user_id` yalnızca personel rolleri                  |
| `POST /appointments/{id}/cancel`    | İptal                                                                 |
| `GET /tickets`                      | Liste (`status` filtresi); hasta yalnızca kendi kayıtları             |
| `POST /tickets`                     | `reference` otomatik (`TKT-…`)                                        |
| `GET /tickets/{reference}`          | Detay                                                                 |

İlk admin kullanıcıyı veritabanında `role=admin` olacak şekilde oluşturman gerekir (bir sonraki adımda seed/invite eklenebilir).

```bash
cd backend
pip install -e ".[dev]"
alembic upgrade head   # readyz için Postgres gerekir
uvicorn hospitai.api.main:app --reload --host 0.0.0.0 --port 8000
```

## Veritabanı (PostgreSQL)

- **ORM**: SQLAlchemy 2 (async `asyncpg`), modeller `src/hospitai/infrastructure/db/models/`.
- **Multi-tenant**: Tüm operasyonel tablolar `tenant_id` ile `tenants` tablosuna bağlıdır; `audit_logs.tenant_id` isteğe bağlıdır (platform olayları).
- **Migrasyonlar**: Alembic. Uygulama `DATABASE_URL` içinde `+asyncpg` kullanır; Alembic DDL için bunu otomatik `+psycopg` (sync) yapar.

```bash
cd backend
cp .env.example .env   # gerekirse DATABASE_URL’i düzenle (ör. farklı Postgres portu)
pip install -e ".[dev]"
alembic upgrade head
```

Yeni revizyon (şema değişince):

```bash
alembic revision --autogenerate -m "kisa_aciklama"
alembic upgrade head
```

## Celery worker (RAG embedding reindex)

Redis (`infra/docker-compose.yml` içindeki `redis` servisi) broker olarak kullanılır. `backend/.env` içinde `CELERY_BROKER_URL` (varsayılan `redis://127.0.0.1:6379/0`) tanımlı olmalı.

Ayrı bir terminalde, `agent` paketinin kurulu olduğu ortamda:

```bash
cd backend
pip install -e ../agent
pip install -e ".[dev]"
celery -A hospitai.workers.celery_app worker -l INFO
```

- **`POST /api/v1/documents/{id}/reindex-embeddings`** (admin/staff): işi kuyruğa atar, `202` ile `task_id` döner.
- Tamamlanmış (`completed`) dokümanların SQL’deki chunk metinleri yeniden embed edilir ve Chroma güncellenir.

## Geliştirme

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ruff check src tests alembic
ruff format src tests alembic
pytest
```
