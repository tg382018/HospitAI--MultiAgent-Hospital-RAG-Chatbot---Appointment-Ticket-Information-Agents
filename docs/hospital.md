# Hospital API — Reference HIS

The `hospital/` directory contains a reference Hospital Information System (HIS) implementation. It is **not a mock** — it uses SQLite with real persistence and enforces the appointment contract the platform agent expects.

Use it to develop and test the appointment booking flow end-to-end without needing a real HIS integration.

## Running locally

```bash
cd hospital
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn xyz_hospital.main:app --reload --port 8010
```

Or via Docker Compose (recommended):

```bash
npm run docker:up     # starts hospital API at http://localhost:8010
```

## Endpoints

| Method | Path               | Description                                                  |
| ------ | ------------------ | ------------------------------------------------------------ |
| GET    | `/health`          | Health check                                                 |
| GET    | `/v1/doctors`      | List seeded doctors                                          |
| GET    | `/v1/slots`        | Available slots — params: `doctor_code`, `date` (YYYY-MM-DD) |
| POST   | `/v1/appointments` | Book an appointment                                          |

## Booking request body

```json
{
  "given_name": "Ali",
  "family_name": "Yılmaz",
  "national_id": "12345678901",
  "department_code": "cardiology",
  "doctor_code": "dr_001",
  "slot_start": "2026-05-20T09:00:00",
  "slot_end": "2026-05-20T09:30:00",
  "idempotency_key": "unique-request-id"
}
```

## Booking response

```json
{
  "status": "accepted",
  "appointment_id": "uuid-string",
  "message": "Appointment confirmed."
}
```

Possible `status` values:

| Status        | Meaning                                                             |
| ------------- | ------------------------------------------------------------------- |
| `accepted`    | Appointment booked successfully                                     |
| `slot_full`   | Slot already taken                                                  |
| `rejected`    | Business rule rejection                                             |
| `error`       | Internal error                                                      |
| `unavailable` | System unavailable (set `XYZ_HOSPITAL_AVAILABLE=false` to simulate) |

## Environment variables

| Variable                 | Default                                      | Description                                 |
| ------------------------ | -------------------------------------------- | ------------------------------------------- |
| `XYZ_DATABASE_URL`       | `sqlite+aiosqlite:///./data/xyz_hospital.db` | SQLite database path                        |
| `XYZ_HOSPITAL_AVAILABLE` | `true`                                       | Set to `false` to simulate maintenance mode |

## Connecting a real HIS

To connect a real hospital system instead of this reference implementation, set `external_hospital_base_url` on the tenant record (via admin API) or set `HOSPITAL_BRIDGE_HTTP_BASE_URL` in `backend/.env`. The platform will forward appointment requests to that URL using the same contract.
