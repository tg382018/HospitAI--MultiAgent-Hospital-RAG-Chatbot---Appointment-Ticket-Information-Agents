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

## Pipeline (tool-augmented)

```
input_guardrail
      │
agent_node  ── On the first LLM call of each user turn:
      │        OpenAI intent classifier (low temperature) runs on the
      │        latest message (+ short history). Unless intent is
      │        clearly `complaint`, complaint/ticket tools are hidden
      │        from the model so greetings do not open ticket flows.
      ├── (optional) tool_executor_node ⟲  (loops up to max)
      │
output_guardrail
```

The conversational model uses `bind_tools`; it may call appointment, RAG, doctor list, or (when allowed) complaint tools. Classification for gating is implemented in `intent.py` (`classify_turn_for_tools`) and invoked from `agent_node`.

**Note:** Each user turn may incur **two** lightweight OpenAI calls on the first agent step when keys are configured: one for intent gating (~JSON), one for the main chat model.

**intent gating** — `intent.py` runs a dedicated OpenAI classification step (low temperature) before the first tool-eligible call each turn. It can hide complaint/ticket tools when the user message is clearly a greeting or non-complaint topic.

**Tool loop** — the main model may call DB/HIS/RAG tools; results are fed back as `ToolMessage`s until the model returns text or hits the loop cap.

**RAG** — document search is triggered via the `search_hospital_info` tool (Chroma + embeddings), not a separate graph node.

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
