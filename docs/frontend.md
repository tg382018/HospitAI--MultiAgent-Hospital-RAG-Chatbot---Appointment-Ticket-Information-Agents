# Frontend — Patient Chat UI

React + Vite application. Serves the patient-facing AI chat interface.

## Structure

```
frontend/src/
├── ChatApp.tsx     # Main chat component (SSE streaming, message list, auth)
├── App.tsx         # Root — loads branding config, renders ChatApp
├── lib/
│   └── api.ts      # apiFetch helper + streamChat (SSE client)
└── index.css       # Tailwind base styles
```

## Environment

| Variable            | Required | Description                                                               |
| ------------------- | -------- | ------------------------------------------------------------------------- |
| `VITE_API_BASE_URL` | No       | Backend URL. Empty = same origin (Vite proxy in dev).                     |
| `VITE_TENANT_SLUG`  | Yes      | Hospital slug used for branding and chat config. Default: `demo-hospital` |

Copy template:

```bash
cp frontend/.env.example frontend/.env
```

In development the Vite proxy forwards `/api/*` and `/ws/*` to `http://localhost:8000`.

## Dev server

```bash
npm run dev           # starts at http://localhost:5173
```

## How SSE streaming works

`streamChat()` in `lib/api.ts` connects to `POST /api/v1/chat/stream` and processes three event types:

| Event   | Payload                                       | Description                    |
| ------- | --------------------------------------------- | ------------------------------ |
| `meta`  | `{ conversation_id }`                         | Fired once at start            |
| `token` | `{ text }`                                    | Each LLM token as it generates |
| `final` | `{ message, intent, sources, rag_used, ... }` | Full result after stream ends  |

On network errors or 5xx responses the client retries up to 3 times with backoff.

## Build

```bash
npm run build         # output: frontend/dist/
```
