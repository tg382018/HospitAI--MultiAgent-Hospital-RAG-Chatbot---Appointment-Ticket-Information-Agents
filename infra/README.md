# Infra — Docker Compose

Yerel geliştirme için **PostgreSQL 16**, **Redis 7**, **Chroma** (vektör DB) ve isteğe bağlı **XYZ Hospital** referans API’si tanımlıdır.

## Hızlı başlangıç

Kök dizinden (varsayılan kullanıcı/şifre/portlar `docker-compose.yml` içinde tanımlı):

```bash
npm run docker:up
```

Durumu görmek için:

```bash
npm run docker:ps
```

Durdurmak (volume’lar kalır):

```bash
npm run docker:down
```

Loglar:

```bash
npm run docker:logs
```

## Ortam dosyası (isteğe bağlı)

Port veya veritabanı bilgilerini değiştirmek için:

```bash
cp infra/env.example infra/.env
```

Docker Compose, `infra/docker-compose.yml` ile aynı klasördeki `infra/.env` dosyasını otomatik okur (`docker compose` proje dizini: `infra/`).

## Uç noktalar (host)

| Servis                          | Host adresi                                    |
| ------------------------------- | ---------------------------------------------- |
| Postgres                        | `127.0.0.1:5432`                               |
| Redis                           | `127.0.0.1:6379`                               |
| Chroma                          | `http://127.0.0.1:8001`                        |
| **XYZ Hospital (referans HIS)** | `http://127.0.0.1:8010` (`/health`, `/v1/...`) |

Chroma konteyner içinde 8000 portunda dinler; FastAPI’nin yerelde 8000 kullanması için host tarafında **8001** eşlemesi kullanılır. **XYZ Hospital** için host **8010** → konteyner 8010 (`XYZ_HOSPITAL_PORT`).

## Backend / frontend env

- `backend/.env.example` → `backend/.env`
- `frontend/.env.example` → `frontend/.env.local`

Şifre veya port değiştirirsen bu dosyaları `infra/.env` ile uyumlu tut.

## Sorun giderme

**Port zaten kullanılıyor** (ör. `6379`, `5432`): `cp infra/env.example infra/.env` yapıp `POSTGRES_PORT`, `REDIS_PORT` veya `CHROMA_HOST_PORT` değerlerini boşta bir porta çevir; `backend/.env` içindeki URL’leri aynı şekilde güncelle.
