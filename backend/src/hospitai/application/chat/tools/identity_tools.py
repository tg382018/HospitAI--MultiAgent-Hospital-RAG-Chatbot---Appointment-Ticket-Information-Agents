"""Patient identity verification tool."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from state import ChatState

from hospitai.application import patient_identity as pid
from hospitai.infrastructure import hospital_chat_bridge as hosp_bridge
from hospitai.infrastructure.db.session import get_session_factory

from .common import get_tenant

log = structlog.get_logger(__name__)


async def verify_patient_identity_tool(state: ChatState) -> dict[str, Any]:
    """Telefon veya TC + ad-soyad: köprü açıksa format + metadata; değilse yerel DB doğrulama."""
    if (state.user_id or "").strip():
        return {
            "success": True,
            "skipped": True,
            "user_message_tr": (
                "Oturum açmış durumdasınız; randevularınız hesabınıza göre listelenir. "
                "Misafir doğrulaması yalnızca giriş yapmadan yazarken gereklidir."
            ),
        }

    stated = pid.extract_stated_full_name(state.user_message, state.guest_full_name)
    if not stated.strip():
        return {
            "success": False,
            "user_message_tr": (
                "Kayıtlı ad-soyadınızla aynı olacak şekilde adınızı ve soyadınızı yazın "
                "(veya iletişim formundaki ad soyad alanını doldurun)."
            ),
        }

    phone = pid.extract_phone_from_text(state.user_message) or pid.normalize_tr_phone_digits(
        state.guest_phone or ""
    )
    tc_raw = pid.extract_tc_from_text(state.user_message) or pid.normalize_tc(
        state.guest_national_id or ""
    )
    tc = tc_raw if tc_raw and pid.is_valid_turkish_national_id(tc_raw) else None

    if not phone and not tc:
        return {
            "success": False,
            "user_message_tr": (
                "Randevu ve talepler için kayıtlı cep telefon numaranızı "
                "(ör. 05xx xxx xx xx) ve ad-soyadınızı yazın. "
                "Kimlik numaranızı yalnızca hastanenin resmi güvenli kanallarında paylaşın."
            ),
        }

    conv_key = (state.conversation_id or "").strip()
    if not conv_key:
        return {
            "success": False,
            "user_message_tr": (
                "Önce bir mesaj göndererek sohbet oturumunu başlatın, ardından tekrar deneyin."
            ),
        }

    try:
        conv_uuid = uuid.UUID(conv_key)
    except (ValueError, TypeError):
        return {"success": False, "user_message_tr": "Geçersiz sohbet oturumu."}

    from sqlalchemy import select

    from hospitai.infrastructure.db.models.conversation import Conversation

    patient_user_id_str = ""

    async with get_session_factory()() as session:
        tenant = await get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "user_message_tr": "Hastane bulunamadı."}

        if hosp_bridge.bridge_is_configured(tenant):
            crow = await session.execute(
                select(Conversation).where(
                    Conversation.id == conv_uuid,
                    Conversation.tenant_id == tenant.id,
                )
            )
            conv = crow.scalar_one_or_none()
            if conv is None:
                return {"success": False, "user_message_tr": "Sohbet oturumu bulunamadı."}
            meta = dict(conv.extra) if conv.extra else {}
            bridge_id: dict[str, str] = {"full_name": stated.strip()[:255]}
            if tc:
                bridge_id["national_id"] = tc
            if phone:
                bridge_id["phone"] = phone
            meta["patient_bridge_identity"] = bridge_id
            conv.extra = meta
            await session.commit()
            return {
                "success": True,
                "user_message_tr": (
                    "İletişim bilgileriniz alındı. Randevu veya talep işlemleri hastane sistemine "
                    "iletilmeye hazır."
                ),
            }

        patient = None
        matched_by_phone = False
        if phone:
            patient = await pid.find_patient_by_phone(
                session, tenant_id=tenant.id, phone_digits=phone
            )
            if patient is not None:
                matched_by_phone = True
        if patient is None and tc:
            patient = await pid.find_patient_by_national_id(
                session,
                tenant_id=tenant.id,
                national_id=tc,
            )

        if patient is None:
            return {
                "success": False,
                "user_message_tr": (
                    "Bu bilgilerle bu hastanede kayıtlı hasta bulunamadı. "
                    "Kayıtlı cep telefonunuzu ve ad-soyadınızı kontrol edin veya "
                    "kayıt için hastane müracaatını kullanın."
                ),
            }

        if not pid.names_match(stated=stated, stored=patient.full_name):
            return {
                "success": False,
                "user_message_tr": (
                    "Ad-soyad bilgisi sistemdeki kayıtla eşleşmedi. Lütfen kayıtlı ad-soyadınızla "
                    "aynı şekilde yazın."
                ),
            }

        crow = await session.execute(
            select(Conversation).where(
                Conversation.id == conv_uuid,
                Conversation.tenant_id == tenant.id,
            )
        )
        conv = crow.scalar_one_or_none()
        if conv is None:
            return {"success": False, "user_message_tr": "Sohbet oturumu bulunamadı."}

        meta = dict(conv.extra) if conv.extra else {}
        pv: dict[str, str] = {"patient_user_id": str(patient.id)}
        if matched_by_phone and phone:
            pv["phone_last4"] = phone[-4:]
        if tc:
            pv["national_id_last4"] = tc[-4:]
        meta["patient_verification"] = pv
        conv.extra = meta
        patient_user_id_str = str(patient.id)
        await session.commit()

    return {
        "success": True,
        "patient_user_id": patient_user_id_str or None,
        "user_message_tr": (
            "Doğrulama tamam. Randevularınızı veya yeni randevu talebinizi söyleyebilirsiniz."
        ),
    }
