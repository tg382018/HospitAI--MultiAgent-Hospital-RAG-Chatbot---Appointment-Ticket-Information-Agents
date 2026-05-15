# Infra — Docker Compose

Local data layer for development. Defined in `infra/docker-compose.yml`.

## Services

| Service        | Image                  | Host port | Description       |
| -------------- | ---------------------- | --------- | ----------------- |
| `postgres`     | postgres:16-alpine     | 5432      | Primary database  |
| `redis`        | redis:7-alpine         | 6379      | Celery broker     |
| `chroma`       | chromadb/chroma:latest | 8001      | Vector database   |
| `xyz-hospital` | built from `hospital/` | 8010      | Reference HIS API |

> ChromaDB listens on port 8000 inside the container. It is mapped to **8001** on the host to avoid colliding with the FastAPI backend (also on 8000).

## Commands

All commands run from the repo root:

```bash
npm run docker:up      # start all services (builds hospital image on first run)
npm run docker:down    # stop all services (volumes are preserved)
npm run docker:ps      # show container status
npm run docker:logs    # follow logs from all services
```

## Custom ports

If a default port is already in use on your machine:

```bash
cp infra/.env.example infra/.env
```

Edit `infra/.env`:

```env
POSTGRES_PORT=5433     # change if 5432 is taken
REDIS_PORT=6380
CHROMA_HOST_PORT=8002
XYZ_HOSPITAL_PORT=8011
```

Then update the matching values in `backend/.env` (`DATABASE_URL`, `CHROMA_PORT`, `CELERY_BROKER_URL`).

## Volumes

Data is persisted in named Docker volumes:

| Volume              | Contents               |
| ------------------- | ---------------------- |
| `postgres_data`     | All application data   |
| `redis_data`        | Celery task queue      |
| `chroma_data`       | Document embeddings    |
| `xyz_hospital_data` | Reference HIS database |

To reset everything (⚠ destroys all local data):

```bash
npm run docker:down
docker volume rm hospitai_postgres_data hospitai_redis_data hospitai_chroma_data hospitai_xyz_hospital_data
npm run docker:up
```
