# HospitAI

An AI-powered hospital assistant platform. Hospitals deploy this system so patients can book appointments, ask medical questions, and submit complaints — all through a conversational AI chat interface.

```
HospitAI/
├── frontend/       # Patient chat UI        (React + Vite)
├── hospital/
│   ├── admin/      # Hospital admin panel   (React + Vite)
│   └── src/        # Reference hospital API (FastAPI + SQLite)
├── agent/          # LangGraph AI agent     (Python package)
├── backend/        # Platform API           (FastAPI + PostgreSQL)
├── infra/          # Local data layer       (Docker Compose)
└── docs/           # Component documentation
```

---

## Purpose

HospitAI is a **multi-tenant** platform: one deployment can serve multiple hospitals, each with their own branding, documents, users, and configuration.

Key capabilities:

- **Conversational AI** — patients chat with an AI agent that understands intent (appointment booking, complaints, general medical questions)
- **RAG** — the agent retrieves answers from hospital-uploaded documents (policies, FAQs, etc.)
- **Appointment integration** — the agent connects to the hospital's existing HIS (Hospital Information System) to fetch slots and book appointments
- **Admin panel** — hospital staff manage documents, branding, users, and system configuration

---

## Architecture

### System diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│                                                             │
│   ┌──────────────────┐        ┌──────────────────────────┐  │
│   │  Patient Chat UI │        │   Hospital Admin Panel   │  │
│   │  :5173 (dev)     │        │   :5174 (dev)            │  │
│   └────────┬─────────┘        └────────────┬─────────────┘  │
└────────────│──────────────────────────────│────────────────┘
             │ /api/* (Vite proxy)          │ /api/*
             ▼                              ▼
┌────────────────────────────────────────────────────────────┐
│                  Backend  :8000  (FastAPI)                  │
│                                                            │
│   Auth · Appointments · Tickets · Documents · Admin        │
│                      │                                     │
│            ┌─────────▼──────────┐                          │
│            │   hospitai-agent   │  (LangGraph package)     │
│            │                    │                          │
│            │  guardrail         │                          │
│            │  → intent          │                          │
│            │  → RAG / tools     │──────────► OpenAI API    │
│            │  → generate        │                          │
│            │  → verify          │                          │
│            └─────────┬──────────┘                          │
└──────────────────────│─────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────────┐
        ▼              ▼                  ▼
  PostgreSQL       ChromaDB           Redis
  (users, appts,  (document          (Celery
  tickets, docs)   embeddings)        broker)
                                       │
                                       ▼
                                  Celery Worker
                                  (reindex embeddings)

                              Hospital HIS API  :8010
                              (xyz_hospital reference impl.)
```

### Chat request flow

```
Patient types message
       │
       ▼
POST /api/v1/chat/stream  (SSE)
       │
       ▼
Backend validates JWT & tenant context
       │
       ▼
hospitai-agent  ──  LangGraph pipeline
  1. input_guardrail      — safety check
  2. classify_intent      — appointment / complaint / medical / general
  3. route_by_intent
  4a. handle_appointment  — calls HIS API via tools
  4b. handle_complaint    — creates ticket
  4c. retrieve_context    — Chroma vector search
       └─ grade_relevance
       └─ augment_web (Tavily, optional)
  5. generate_response    — OpenAI LLM
  6. verify_response      — self-check, retry once if weak
  7. output_guardrail     — final safety filter
       │
       ▼
SSE tokens stream back to browser in real-time
```

---

## Technologies

| Layer           | Technology                                   |
| --------------- | -------------------------------------------- |
| Patient UI      | React 18, Vite, TypeScript, Tailwind CSS     |
| Admin UI        | React 18, Vite, TypeScript, Tailwind CSS     |
| Backend API     | Python 3.11+, FastAPI, Uvicorn               |
| AI agent        | LangGraph, LangChain, OpenAI (GPT-4o)        |
| RAG             | ChromaDB, OpenAI text-embedding-3-small      |
| Database        | PostgreSQL 16, SQLAlchemy 2 (async), Alembic |
| Auth            | JWT (PyJWT), bcrypt                          |
| Background jobs | Celery 5, Redis                              |
| Rate limiting   | SlowAPI                                      |
| Logging         | structlog (JSON in production)               |
| Hospital API    | FastAPI, SQLite, aiosqlite                   |
| Infrastructure  | Docker Compose                               |
| Code quality    | Ruff, Prettier, ESLint, Husky                |

---

## Quick start

### Prerequisites

- Docker Desktop
- Node.js 20+
- Python 3.11+

### 1 — Clone and install JS dependencies

```bash
git clone <repo-url>
cd HospitAI
npm install
```

### 2 — Start the data layer

```bash
npm run docker:up
```

Starts Postgres, Redis, ChromaDB, and the reference hospital API. On first run the `hospital` image is built (~1 min).

Optional — customize ports (e.g. if 5432 is already in use):

```bash
cp infra/.env.example infra/.env
# edit infra/.env, then also update DATABASE_URL port in backend/.env
```

### 3 — Configure the backend

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and fill in the **three required values**:

```env
OPENAI_API_KEY=sk-...          # your OpenAI key
JWT_SECRET=<run: openssl rand -hex 32>
ADMIN_REGISTRATION_KEY=<choose a secret key>
```

Everything else works with the Docker Compose defaults.

### 4 — Set up the Python environment

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ../agent
pip install -e ".[dev]"
alembic upgrade head            # creates tables + seeds demo-hospital tenant
```

### 5 — Copy frontend env files

```bash
cp frontend/.env.example frontend/.env
cp hospital/admin/.env.example hospital/admin/.env
```

Edit `hospital/admin/.env` and set `VITE_HOSPITAL_NAME` to your hospital's name.

### 6 — Run the servers

In separate terminals:

```bash
# Backend API
cd backend && uvicorn hospitai.api.main:app --reload --port 8000

# Patient chat UI
npm run dev

# Admin panel
npm run dev:admin
```

| Service        | URL                        |
| -------------- | -------------------------- |
| Patient chat   | http://localhost:5173      |
| Admin panel    | http://localhost:5174      |
| Backend API    | http://localhost:8000      |
| API docs (dev) | http://localhost:8000/docs |
| ChromaDB       | http://localhost:8001      |
| Hospital API   | http://localhost:8010      |

---

## npm scripts

| Command               | Description                                    |
| --------------------- | ---------------------------------------------- |
| `npm run docker:up`   | Start Postgres + Redis + Chroma + hospital API |
| `npm run docker:down` | Stop all containers (volumes persist)          |
| `npm run docker:ps`   | Container status                               |
| `npm run docker:logs` | Follow all container logs                      |
| `npm run dev`         | Patient chat dev server                        |
| `npm run dev:admin`   | Admin panel dev server                         |
| `npm run build`       | Build both frontends                           |
| `npm run format`      | Prettier (TS/JS/CSS/JSON/YAML/MD)              |
| `npm run lint`        | ESLint (frontend + admin)                      |

---

## Component documentation

| Doc                                  | Contents                            |
| ------------------------------------ | ----------------------------------- |
| [docs/backend.md](docs/backend.md)   | API routes, auth, DB, Celery worker |
| [docs/agent.md](docs/agent.md)       | LangGraph pipeline, nodes, tools    |
| [docs/frontend.md](docs/frontend.md) | Patient chat UI, env config         |
| [docs/hospital.md](docs/hospital.md) | Reference HIS API endpoints         |
| [docs/infra.md](docs/infra.md)       | Docker Compose services and ports   |
