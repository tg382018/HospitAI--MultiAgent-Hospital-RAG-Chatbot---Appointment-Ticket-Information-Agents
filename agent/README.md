# `agent/` — `hospitai-agent`

Bu dizin **ayrı bir Python paketidir** (`pyproject.toml` → dağıtım adı `hospitai-agent`, import adı `hospitai_agent`).

## İçerik

- **LangGraph** (`graph.py`): intent, güvenlik, yanıt üretimi.
- **LLM** (`llm_profile.py`, `llm_client.py`, `intent.py`, `safety.py`): `configure_llm_profile(...)` lifespan’da.
- **RAG / vektör** (`rag_profile.py`, `chunking.py`, `embeddings.py`, `vector_db.py`): `configure_rag_profile(...)` lifespan’da (Chroma, OpenAI embedding, tiktoken chunk boyutları).
- **Tool sözleşmesi** (`workflow_tools.py`): `ChatWorkflowTools` — platform `application/chat/tools.py` + `configure_workflow_tools(make_workflow_tools())`.

## Kurulum (geliştirici)

```bash
cd agent && pip install -e .
cd ../backend && pip install -e ../agent && pip install -e ".[dev]"
```

Platform backend tek process’tedir; ileride agent ayrı worker olursa HTTP ile delege edilir.
