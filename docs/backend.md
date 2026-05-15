# Backend

FastAPI service. Runs on port `8000`. The `hospitai-agent` package is imported in-process.

## Layer structure

```
backend/src/hospitai/
├── api/            # HTTP/WebSocket layer (routers, schemas, middleware)
├── application/    # Use cases and port interfaces (no framework dependencies)
├── infrastructure/ # DB models, JWT, password hashing, hospital connector
├── domain/         # Core rules and types
└── workers/        # Celery worker (embedding reindex)
```

## Key endpoints

| Method    | Path                                   | Description                                                |
| --------- | -------------------------------------- | ---------------------------------------------------------- |
| GET       | `/healthz`                             | Liveness probe                                             |
| GET       | `/readyz`                              | Readiness probe (requires DB)                              |
| POST      | `/api/v1/auth/login`                   | Login → access + refresh tokens                            |
| POST      | `/api/v1/auth/register`                | Patient self-registration (if enabled)                     |
| POST      | `/api/v1/auth/register-admin`          | Admin account creation (requires `ADMIN_REGISTRATION_KEY`) |
| POST      | `/api/v1/auth/refresh`                 | Refresh access token                                       |
| GET       | `/api/v1/users/me`                     | Current user profile                                       |
| POST      | `/api/v1/chat/stream`                  | SSE chat stream                                            |
| GET       | `/api/v1/appointments/available-slots` | Available slots from HIS                                   |
| GET/POST  | `/api/v1/appointments`                 | List / create appointments                                 |
| GET/POST  | `/api/v1/tickets`                      | List / create tickets                                      |
| GET/POST  | `/api/v1/documents`                    | Document management (admin/staff)                          |
| GET/PATCH | `/api/v1/admin/tenant-policy`          | RAG and feature flags                                      |
| GET/PATCH | `/api/v1/admin/users/{id}`             | User management                                            |
| GET/PATCH | `/api/v1/admin/chat-branding`          | Chat UI branding (logo, name, colors)                      |

API docs available at `http://localhost:8000/docs` when `ENVIRONMENT != production`.

## Authentication

- JWT Bearer tokens. Login via `POST /api/v1/auth/login` with `tenant_slug`, `email`, `password`.
- Roles: `patient`, `staff`, `admin`.
- Rate limits (per IP): login 30/min, register 15/min, refresh 60/min.

## Database

PostgreSQL 16. Async via SQLAlchemy 2 + asyncpg.

All operational tables carry a `tenant_id` foreign key — the schema is fully multi-tenant.

**Run migrations:**

```bash
cd backend
alembic upgrade head
```

**Create a new migration after model changes:**

```bash
alembic revision --autogenerate -m "short_description"
alembic upgrade head
```

## Celery worker

Handles async document embedding reindex jobs.

```bash
cd backend
celery -A hospitai.workers.celery_app worker -l INFO
```

Trigger via: `POST /api/v1/documents/{id}/reindex-embeddings` (admin/staff) → returns `202` with `task_id`.

## Running locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ../agent
pip install -e ".[dev]"
cp .env.example .env        # fill in OPENAI_API_KEY, JWT_SECRET, ADMIN_REGISTRATION_KEY
alembic upgrade head
uvicorn hospitai.api.main:app --reload --port 8000
```

## Code quality

```bash
ruff check src tests alembic
ruff format src tests alembic
pytest
```
