"""Hastane chat köprüsü: HTTP API veya RabbitMQ (Kombu) ile randevu / talep iletimi.

HTTP (tercih): ``POST {base}/v1/hospitai-bridge/{operation}``

- ``appointments/query`` — ``tenant_slug``, ``full_name``, isteğe bağlı ``phone`` ve/veya
  ``national_id``, ``conversation_id``
- ``appointments/book`` — ``full_name``, ``starts_at``, ``ends_at``, ``doctor_name``, isteğe bağlı
  ``phone`` ve/veya ``national_id``, ``department_name``, ``conversation_id``
- ``appointments/cancel`` — ``full_name``, isteğe bağlı ``phone`` ve/veya ``national_id``,
  ``appointment_id``, ``user_message``
- ``tickets/query`` — ``full_name``, isteğe bağlı ``phone`` ve/veya ``national_id``
- ``tickets/create`` — ``full_name``, ``subject``, ``description``, isteğe bağlı ``phone``,
  ``national_id``, ``email``

İstek gövdesi her zaman ``tenant_slug`` içerir; Bearer için tenant
``external_hospital_api_key`` kullanılır.

Beklenen yanıt (esnek JSON):

- ``accepted`` veya ``status`` ∈ {accepted, ok, success}
- ``message`` — kullanıcıya gösterilecek metin
- ``appointments`` / ``tickets`` — liste
- ``reference`` — talep referansı vb.

RabbitMQ: ``HOSPITAL_BRIDGE_RABBITMQ_URL`` tanımlı ve HTTP tabanı **yoksa** aynı payload
``hospitai.bridge`` topic exchange üzerinden ``hospitai.{operation}`` routing key ile yayınlanır
(geri dönüş yok; onay için hastane tarafı SMS / webhook kullanır).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
import structlog

from hospitai.infrastructure.settings import Settings, get_settings

log = structlog.get_logger(__name__)


def bridge_http_base_url(tenant: Any, settings: Settings | None = None) -> str:
    """Önce tenant dış API tabanı, yoksa global ``HOSPITAL_BRIDGE_HTTP_BASE_URL``."""
    s = settings or get_settings()
    t = (getattr(tenant, "external_hospital_base_url", None) or "").strip()
    if t:
        return t.rstrip("/")
    return (s.hospital_bridge_http_base_url or "").strip().rstrip("/")


def bridge_is_configured(tenant: Any, settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(bridge_http_base_url(tenant, s) or (s.hospital_bridge_rabbitmq_url or "").strip())


def _auth_headers(api_key: str | None) -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key.strip()}"
    return h


def _rabbit_publish_sync(
    broker_url: str, tenant_slug: str, operation: str, payload: dict[str, Any]
) -> None:
    from kombu import Connection, Exchange

    envelope = {
        "tenant_slug": tenant_slug,
        "operation": operation,
        "payload": payload,
    }
    routing_key = f"hospitai.{operation.replace('/', '.')}"
    ex = Exchange("hospitai.bridge", type="topic", durable=False)
    with Connection(broker_url) as conn, conn.Producer(serializer="json") as producer:
        producer.publish(envelope, exchange=ex, routing_key=routing_key, declare=[ex])


def _normalize_http_result(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    st = str(body.get("status") or "").lower()
    accepted = bool(body.get("accepted"))
    if st in {"accepted", "ok", "success", "true", "1"}:
        accepted = True
    if status_code >= 400:
        msg = str(body.get("message") or body.get("error") or "Hastane isteği başarısız oldu.")
        return {
            "success": False,
            "accepted": False,
            "user_message_tr": msg,
            "raw": body,
        }
    msg = str(body.get("message") or "").strip()
    if not accepted and not msg:
        msg = "Hastane yanıtı işlenemedi."
    return {
        "success": accepted,
        "accepted": accepted,
        "user_message_tr": msg or ("İşlem kabul edildi." if accepted else "İşlem kabul edilmedi."),
        "appointments": body.get("appointments")
        if isinstance(body.get("appointments"), list)
        else [],
        "tickets": body.get("tickets") if isinstance(body.get("tickets"), list) else [],
        "reference": str(body.get("reference") or ""),
        "raw": body,
    }


async def dispatch_hospital_bridge(
    *,
    tenant_slug: str,
    tenant: Any,
    operation: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """HTTP varsa POST; yoksa Rabbit varsa yayınla. İkisi de yoksa ``None``."""
    settings = get_settings()
    base = bridge_http_base_url(tenant, settings)
    api_key = (getattr(tenant, "external_hospital_api_key", None) or "").strip() or None
    body = {"tenant_slug": tenant_slug, **payload}

    if base:
        url = f"{base}/v1/hospitai-bridge/{operation}"
        try:
            async with httpx.AsyncClient(timeout=35.0) as client:
                r = await client.post(url, json=body, headers=_auth_headers(api_key))
                try:
                    data = r.json() if r.content else {}
                except json.JSONDecodeError:
                    data = {"message": r.text[:500]}
                if not isinstance(data, dict):
                    data = {"message": str(data)}
                out = _normalize_http_result(r.status_code, data)
                if settings.hospital_bridge_rabbitmq_url and out.get("accepted"):
                    try:
                        await asyncio.to_thread(
                            _rabbit_publish_sync,
                            settings.hospital_bridge_rabbitmq_url.strip(),
                            tenant_slug,
                            operation,
                            body,
                        )
                    except Exception as exc:
                        log.warning("bridge_rabbit_mirror_failed", error=str(exc))
                return out
        except httpx.HTTPError as exc:
            log.warning("bridge_http_error", url=url, error=str(exc))
            return {
                "success": False,
                "accepted": False,
                "user_message_tr": (
                    "Hastane sistemine şu an ulaşılamıyor. Lütfen daha sonra tekrar deneyin "
                    "veya randevu hattını arayın."
                ),
                "raw": {},
            }

    rabbit = (settings.hospital_bridge_rabbitmq_url or "").strip()
    if rabbit:
        try:
            await asyncio.to_thread(_rabbit_publish_sync, rabbit, tenant_slug, operation, body)
        except Exception as exc:
            log.warning("bridge_rabbit_publish_failed", error=str(exc))
            return {
                "success": False,
                "accepted": False,
                "user_message_tr": "Mesaj kuyruğuna iletim başarısız oldu.",
                "raw": {},
            }
        return {
            "success": True,
            "accepted": None,
            "bridge_queued": True,
            "user_message_tr": (
                "İstek hastane mesaj kuyruğuna iletildi. Onay ve saat bilgisi hastane tarafından "
                "size iletilecektir."
            ),
            "appointments": [],
            "tickets": [],
            "reference": "",
            "raw": {},
        }

    return None


def extract_uuid_from_text(text: str) -> str | None:
    m = re.search(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        text or "",
    )
    return m.group(0) if m else None
