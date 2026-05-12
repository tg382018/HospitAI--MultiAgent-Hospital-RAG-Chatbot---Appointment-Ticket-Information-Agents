# HospitAI Backend

Python / FastAPI servisi. Katmanlar:

- `domain/` — kurallar ve modeller (framework bağımsız)
- `application/` — use case’ler ve port arayüzleri
- `infrastructure/` — DB, cache, dış servis implementasyonları
- `api/` — HTTP/WebSocket sunumu

## Geliştirme

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ruff check src tests
ruff format src tests
```
