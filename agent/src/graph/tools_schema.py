"""OpenAI function-calling tool schemas for the hospital agent.

Each tool maps to a backend WorkflowTools callable. The LLM decides which
tools to invoke and extracts structured parameters — no regex keyword matching.
"""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_available_slots",
            "description": (
                "Hastanede müsait randevu slotlarını listele. "
                "Kullanıcı randevu almak, boş saatleri görmek veya hangi doktor/bölüm "
                "müsait diye sorduğunda çağır."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department_name": {
                        "type": "string",
                        "description": "Bölüm adı (Dahiliye, Kardiyoloji, Ortopedi…). Bilinmiyorsa boş bırak.",
                    },
                    "doctor_name": {
                        "type": "string",
                        "description": "Doktor adı. Bilinmiyorsa boş bırak.",
                    },
                    "target_date": {
                        "type": "string",
                        "description": "ISO tarih (2026-05-15), 'bugün' veya 'yarın'. Belirtilmezse bugün.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": (
                "Randevu oluştur. Kullanıcı saat seçip kimlik bilgilerini (ad + telefon) "
                "sağladıktan sonra çağır. Eksik bilgi varsa önce kullanıcıya sor, "
                "sonra bu aracı çağır."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "starts_at": {
                        "type": "string",
                        "description": (
                            "Randevu başlangıcı: Türkiye saati ile ISO datetime, mutlaka +03:00 ofseti kullan "
                            "(örn. 2026-05-16T11:00:00+03:00). list_available_slots çıktısındaki saatlerle "
                            "aynı saat diliminde olmalı; asla +00:00 ile 'yerel saat' gösterme."
                        ),
                    },
                    "doctor_name": {"type": "string", "description": "Doktor adı."},
                    "department_name": {"type": "string", "description": "Bölüm adı."},
                    "patient_name": {
                        "type": "string",
                        "description": "Hastanın tam adı (ad soyad). Mesajdan çıkar.",
                    },
                    "patient_phone": {
                        "type": "string",
                        "description": "Cep telefonu. Mesajdan çıkar (ör. 05075824166).",
                    },
                    "patient_national_id": {
                        "type": "string",
                        "description": "TC kimlik numarası (11 hane, opsiyonel).",
                    },
                },
                "required": ["starts_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_my_appointments",
            "description": "Hastanın mevcut randevularını listele.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name": {"type": "string"},
                    "patient_phone": {"type": "string"},
                    "patient_national_id": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Randevu iptal et.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_reference": {
                        "type": "string",
                        "description": "Randevu UUID veya referans kodu (biliniyorsa).",
                    },
                    "patient_name": {"type": "string"},
                    "patient_phone": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_complaint_ticket",
            "description": "Yeni şikayet veya talep oluştur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Şikayet konusu (kısa başlık)."},
                    "description": {"type": "string", "description": "Detaylı açıklama."},
                    "patient_name": {"type": "string", "description": "Hasta adı soyadı (mesajdan çıkar)."},
                    "patient_phone": {"type": "string", "description": "Telefon numarası (mesajdan çıkar)."},
                },
                "required": ["subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_complaint_tickets",
            "description": "Şikayet/talep listesini göster veya belirli bir TKT referansını sorgula.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_reference": {
                        "type": "string",
                        "description": "TKT-xxx formatında referans (belirli bir talep sorgulanıyorsa).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_complaint_ticket",
            "description": "Bir şikayet veya talebi kapat (çözüldü olarak işaretle).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_reference": {
                        "type": "string",
                        "description": "Kapatılacak talebin TKT-xxx referansı.",
                    },
                },
                "required": ["ticket_reference"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_doctors",
            "description": (
                "Hastanedeki aktif doktorları ve bölümlerini DB'den listele. "
                "Kullanıcı 'hangi doktorlar var', 'X bölümünde kim var', 'doktor ismi nedir' "
                "veya belirli bir uzmanlıktan doktor sorduğunda çağır. "
                "Gerçek DB verisi döner — bu araç RAG'dan önce gelir."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department_name": {
                        "type": "string",
                        "description": "Bölüm adı filtresi (ör. 'Dahiliye', 'Kardiyoloji'). Boş bırakılırsa tüm bölümler.",
                    },
                    "doctor_name": {
                        "type": "string",
                        "description": "Doktor adı filtresi. Boş bırakılırsa tüm doktorlar.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_hospital_info",
            "description": (
                "Hastane bilgi tabanında (RAG) arama yap. "
                "YALNIZCA şunlar için kullan: hastane adresi, park, ziyaret saatleri, "
                "sigorta/ödeme bilgisi, genel sağlık/hastalık soruları, "
                "DB araçlarının kapsamamadığı politika/prosedür konuları. "
                "Doktor adları, bölümler ve randevu bilgileri için KULLANMA — bunlar için "
                "list_doctors veya list_available_slots çağır."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Aranacak soru veya konu.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

TOOL_NAMES: frozenset[str] = frozenset(t["function"]["name"] for t in TOOLS)

APPOINTMENT_TOOLS: frozenset[str] = frozenset(
    {"list_available_slots", "book_appointment", "list_my_appointments", "cancel_appointment"}
)
COMPLAINT_TOOLS: frozenset[str] = frozenset(
    {"create_complaint_ticket", "list_complaint_tickets", "close_complaint_ticket"}
)
INFO_TOOLS: frozenset[str] = frozenset({"search_hospital_info", "list_doctors"})
