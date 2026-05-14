#!/usr/bin/env python3
"""Yerel stack açıkken chat akışını hızlı doğrula (Docker + backend/.env gerekir).

Kullanım (backend dizininden):
  python3 scripts/smoke_chat.py

Önce:
  docker compose -f ../infra/docker-compose.yml up -d
  alembic upgrade head
  uvicorn hospitai.api.main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

# backend/ kökünü path'e ekle
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from starlette.testclient import TestClient  # noqa: E402

from hospitai.api.main import create_app  # noqa: E402


def main() -> int:
    # Alembic seed: b2c3d4e5f6a7_seed_demo_tenant → slug 'demo-hospital'
    tenant_slug = os.environ.get("SMOKE_TENANT_SLUG", "demo-hospital")
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    password = "smokepass123456"

    with TestClient(create_app()) as client:
        hz = client.get("/healthz")
        if hz.status_code != 200:
            print("FAIL: /healthz", hz.status_code, hz.text)
            return 1
        print("OK /healthz")

        anon = client.post(
            "/api/v1/chat",
            headers={"X-Tenant-Slug": tenant_slug},
            json={"message": "Merhaba (misafir)."},
        )
        if anon.status_code != 200:
            print("FAIL: anonymous chat", anon.status_code, anon.text[:800])
            return 1
        print("OK anonymous chat intent=", anon.json().get("intent"))

        reg = client.post(
            "/api/v1/auth/register",
            json={
                "tenant_slug": tenant_slug,
                "email": email,
                "password": password,
                "full_name": "Smoke User",
            },
        )
        if reg.status_code != 201:
            print(
                "FAIL: register — Postgres ve migration hazır mı? "
                f"({reg.status_code}) {reg.text[:500]}",
            )
            print(
                "İpucu: migration sonrası varsayılan tenant slug'ı 'demo-hospital'. "
                "Farklı tenant için SMOKE_TENANT_SLUG kullanın.",
            )
            return 1
        token = reg.json()["access_token"]
        print("OK register")

        chat = client.post(
            "/api/v1/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "Merhaba, kısaca kendini tanıt."},
        )
        if chat.status_code != 200:
            print("FAIL: chat", chat.status_code, chat.text[:800])
            return 1
        body = chat.json()
        print("OK chat intent=", body.get("intent"), "len=", len(body.get("message", "")))
        print("--- assistant (ilk 400 karakter) ---")
        print((body.get("message") or "")[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
