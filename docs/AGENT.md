# Agent — `hospitai-agent`

The `agent/` directory is a **standalone Python package** (`hospitai-agent`) that contains the entire AI pipeline. The backend imports it at runtime; they share the same process.

## Package layout

```
agent/src/
├── graph/           # LangGraph pipeline (main entry point)
│   ├── builder.py   # StateGraph assembly, compiled graph cache
│   ├── nodes.py     # All LangGraph nodes (guardrail, intent, RAG, tools, generate, verify)
│   ├── routing.py   # Intent-based edge routing
│   ├── prompts.py   # System prompts per intent
│   ├── quality.py   # RAG grading, Tavily web fallback, response verification
│   ├── streaming.py # SSE token parsing and postprocessing
│   └── chat_runner.py  # run_chat / iter_chat_sse entry points
├── llm/             # LLM client and profile configuration
├── rag/             # Embeddings, chunking, RAG profile
├── vectordb/        # ChromaDB client wrapper
└── tools/           # Tool parameter extraction helpers
```

## Pipeline

```
input_guardrail
      │
classify_intent
      │
route_by_intent
      ├── appointment ──► handle_appointment ──► generate_response
      ├── complaint   ──► handle_complaint   ──► generate_response
      └── medical /       retrieve_context
          hospital /           │
          general    ──► grade_rag_relevance
                               │
                         augment_web_context  (Tavily, optional)
                               │
                         generate_response
                               │
                         verify_response ──(retry once)──► generate_response
                               │
                         output_guardrail
```

**input_guardrail / output_guardrail** — blocks harmful or off-topic content.

**classify_intent** — keyword heuristics + LLM call. Intents: `appointment`, `complaint`, `medical`, `hospital`, `general`.

**retrieve_context** — vector search in ChromaDB against hospital-uploaded documents.

**grade_rag_relevance** — scores retrieved chunks; drops irrelevant ones. If nothing passes, optionally falls back to a Tavily web summary (`TAVILY_API_KEY` required).

**generate_response** — final LLM call with system prompt, conversation history, and retrieved context.

**verify_response** — checks the response addresses the question with evidence. Retries once with stricter instructions; if still weak, returns a safe short fallback.

## Tools (injected by backend)

The backend creates a `ChatWorkflowTools` instance and passes it to the agent via `configure_workflow_tools(...)`. Tools available to the agent:

| Tool                  | Description                                       |
| --------------------- | ------------------------------------------------- |
| `get_available_slots` | Fetch appointment slots from the hospital HIS API |
| `book_appointment`    | Submit an appointment request to the HIS API      |
| `list_appointments`   | List the patient's existing appointments          |
| `create_ticket`       | Create a support/complaint ticket                 |
| `list_tickets`        | List the patient's tickets                        |

## Installation

```bash
cd agent && pip install -e .
# backend also needs the package:
cd ../backend && pip install -e ../agent && pip install -e ".[dev]"
```

## Adding new functionality

- **New node** → `graph/nodes.py` + add edges in `graph/builder.py`
- **New intent** → `intent.py` + `graph/routing.py` + prompt in `graph/prompts.py`
- **New tool** → `workflow_tools.py` interface + backend `application/chat/tools/` implementation + call site in `graph/nodes.py`
