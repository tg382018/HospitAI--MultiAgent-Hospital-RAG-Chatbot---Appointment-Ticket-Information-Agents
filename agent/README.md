# `agent/` — `hospitai-agent`

Bu dizin **ayrı bir Python paketidir** (`pyproject.toml` → dağıtım adı `hospitai-agent`, import adı `hospitai_agent`).

## İçerik

- **LangGraph** sohbet grafiği (`graph.py`): intent, güvenlik, yanıt üretimi.
- **LLM profili** (`llm_profile.py`): FastAPI `lifespan` içinde platform `Settings` ile `configure_llm_profile(...)` doldurulur (API anahtarları vb.).
- **Tool sözleşmesi** (`workflow_tools.py`): `ChatWorkflowTools` — slot listesi, ticket listesi, RAG retrieve; uygulamalar `backend/src/hospitai/application/chat/tools.py` içinde verilir ve `configure_workflow_tools(make_workflow_tools())` ile kaydedilir.

## Kurulum (geliştirici)

```bash
cd agent && pip install -e .
cd ../backend && pip install -e ../agent && pip install -e ".[dev]"
```

Platform backend tek process’tedir; ileride agent ayrı worker olursa tool’lar HTTP ile delege edilir.
