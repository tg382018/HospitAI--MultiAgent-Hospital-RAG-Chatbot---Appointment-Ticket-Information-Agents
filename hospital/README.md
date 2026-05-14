# XYZ Hospital — referans hastane sistemi API’si

Bu servis **mock değildir**: SQLite üzerinde gerçek kalıcılık, iş kuralları ve platformla uyumlu **randevu yanıt sözleşmesi** (`accepted`, `slot_full`, `rejected`, `error`, `unavailable`) sunar.

HospitAI platform agent’ı veya başka bir entegrasyon, bu API’ye HTTP ile bağlanarak uçtan uca test edebilir.

## Çalıştırma

```bash
cd integrations/xyz-hospital
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn xyz_hospital.main:app --reload --port 8010
```

Varsayılan veritabanı: çalışma dizininde `data/xyz_hospital.db` (ilk istekte oluşur). Özelleştirmek için:

```bash
export XYZ_DATABASE_URL=sqlite+aiosqlite:///./data/xyz_hospital.db
export XYZ_HOSPITAL_AVAILABLE=true
```

## Uç noktalar

| Method | Path               | Açıklama                                         |
| ------ | ------------------ | ------------------------------------------------ |
| GET    | `/health`          | Sağlık                                           |
| GET    | `/v1/doctors`      | Seed edilmiş doktor listesi                      |
| GET    | `/v1/slots`        | `doctor_code`, `date` (YYYY-MM-DD) — boş slotlar |
| POST   | `/v1/appointments` | Randevu talebi + `idempotency_key`               |

## POST /v1/appointments gövdesi

- `given_name`, `family_name`, `national_id` (11 haneli TC formatı)
- `department_code`, `doctor_code`
- `slot_start`, `slot_end` (ISO 8601)
- `idempotency_key` (zorunlu, tekrarlayan isteklerde aynı yanıt)

## Yanıt

HTTP 200 + JSON:

- `status`: `accepted` | `slot_full` | `rejected` | `error` | `unavailable`
- `appointment_id`: kabulde UUID string
- `message`: insan okunur açıklama

`unavailable` için `XYZ_HOSPITAL_AVAILABLE=false` yapılabilir (bakım simülasyonu).

Docker: kök `infra/docker-compose.yml` içinde `xyz-hospital` servisi.
