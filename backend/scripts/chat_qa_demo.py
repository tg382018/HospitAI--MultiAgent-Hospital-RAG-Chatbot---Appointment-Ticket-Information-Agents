#!/usr/bin/env python3
"""Birden fazla chat sorusu dene; soru/cevapları stdout'a yaz.

  cd backend && python3 scripts/chat_qa_demo.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from starlette.testclient import TestClient  # noqa: E402

from hospitai.api.main import create_app  # noqa: E402

QUESTIONS = [
    "Merhaba, kısaca ne işe yararsın?",
    "Hastanede hangi bölümler var, özetler misin?",
    "Yarın öğleden sonra randevu almak istiyorum; nasıl ilerlemeliyim?",
    "Şikayet oluşturmak istiyorum: otoparkta uzun süre bekledim.",
    "Teşekkürler, iyi günler.",
]

TENANT = os.environ.get("SMOKE_TENANT_SLUG", "demo-hospital")


def main() -> int:
    email = f"qa-{uuid.uuid4().hex[:10]}@example.com"
    password = "qademopass123456"

    with TestClient(create_app()) as client:
        if client.get("/healthz").status_code != 200:
            print("FAIL: /healthz", file=sys.stderr)
            return 1

        reg = client.post(
            "/api/v1/auth/register",
            json={
                "tenant_slug": TENANT,
                "email": email,
                "password": password,
                "full_name": "QA Demo",
            },
        )
        if reg.status_code != 201:
            print("FAIL: register", reg.status_code, reg.text[:600], file=sys.stderr)
            return 1
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        conv_id: str | None = None
        for i, q in enumerate(QUESTIONS, 1):
            body: dict = {"message": q}
            if conv_id:
                body["conversation_id"] = conv_id
            r = client.post("/api/v1/chat", headers=headers, json=body)
            print(f"\n{'=' * 72}\n### Soru {i}\n{q}\n")
            if r.status_code != 200:
                print(f"[HTTP {r.status_code}]\n{r.text[:1200]}")
                continue
            data = r.json()
            conv_id = data.get("conversation_id") or conv_id
            intent = data.get("intent", "")
            msg = data.get("message") or ""
            print(f"**intent:** `{intent}`  |  **conversation_id:** `{conv_id}`\n")
            print("### Cevap\n")
            print(msg)
        print(f"\n{'=' * 72}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
