# HospitAI Backend

Python / FastAPI servisi. Katmanlar:

- `domain/` — kurallar ve modeller (framework bağımsız)
- `application/` — use case’ler ve port arayüzleri
- `infrastructure/` — DB, cache, dış servis implementasyonları
- `api/` — HTTP/WebSocket sunumu

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
