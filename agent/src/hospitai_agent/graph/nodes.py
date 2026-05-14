"""LangGraph node callables (safety, intent, tools, RAG, LLM)."""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from hospitai_agent.graph.prompts import GENERAL_FALLBACK, SYSTEM_PROMPTS
from hospitai_agent.graph.quality import is_smalltalk_message
from hospitai_agent.graph.registry import get_workflow_tools
from hospitai_agent.graph.routing import (
    has_tc_kimlik_candidate,
    has_tr_phone_candidate,
    wants_book_appointment,
    wants_cancel_appointment,
    wants_complaint_ticket_list,
    wants_my_appointments_list,
    wants_new_complaint_ticket,
    wants_slot_search,
)
from hospitai_agent.graph.state_types import (
    GraphState,
    chat_state_to_graph_state,
    graph_state_to_chat_state,
)
from hospitai_agent.intent import classify_intent
from hospitai_agent.llm_client import get_llm
from hospitai_agent.llm_profile import get_llm_profile, merge_llm_profile
from hospitai_agent.safety import output_safety_check, safety_check
from hospitai_agent.ticket_reference import extract_ticket_reference

log = structlog.get_logger(__name__)


async def input_guardrail(state: GraphState) -> GraphState:
    cs = graph_state_to_chat_state(state)
    cs = await safety_check(cs)
    return chat_state_to_graph_state(cs)


async def classify_intent_node(state: GraphState) -> GraphState:
    if state["safety_flag"]:
        return state
    cs = graph_state_to_chat_state(state)
    profile = merge_llm_profile(get_llm_profile(), cs.llm_overrides or None)
    cs = await classify_intent(cs, llm_profile=profile)
    return chat_state_to_graph_state(cs)


async def retrieve_context(state: GraphState) -> GraphState:
    if state["safety_flag"]:
        return state

    if is_smalltalk_message(state["user_message"]):
        return state

    intent = state["intent"]
    if intent not in {"hospital_info", "medical_info", "general"}:
        return state

    cs = graph_state_to_chat_state(state)
    base = state["user_message"].strip()
    if intent == "hospital_info":
        query = (
            f"{base}\n\n"
            "Arama ipuçları: hastane bölümleri poliklinik klinik doktorlar "
            "ziyaret saatleri iletişim adres otopark refakat hizmetler."
        )
    elif intent == "medical_info":
        query = (
            f"{base}\n\n"
            "Arama ipuçları: genel sağlık bilgisi belirti yönetimi; "
            "kesin tanı veya ilaç dozu önerilmez."
        )
    else:
        query = base

    result = await get_workflow_tools().retrieve_knowledge(cs, query)
    if result.get("success") and (result.get("context") or "").strip():
        state["rag_context"] = result["context"]
        state["rag_used"] = True
        state["sources"] = result.get("sources", [])
    return state


async def handle_appointment(state: GraphState) -> GraphState:
    cs = graph_state_to_chat_state(state)
    msg = state["user_message"]
    wants_list = wants_my_appointments_list(msg)
    wants_slots = wants_slot_search(msg)
    wants_book = wants_book_appointment(msg)
    wants_cancel = wants_cancel_appointment(msg)
    has_tc = has_tc_kimlik_candidate(msg)
    has_phone = has_tr_phone_candidate(msg)
    guest_phone_ok = bool((state.get("guest_phone") or "").strip())
    guest_name_ok = len((state.get("guest_full_name") or "").strip()) >= 3
    has_guest_identity = guest_phone_ok and guest_name_ok

    if not wants_book and not wants_list and not wants_slots and not wants_cancel:
        wants_slots = True

    if (has_tc or has_phone or has_guest_identity) and not (state.get("user_id") or "").strip():
        vr = await get_workflow_tools().verify_patient_identity(cs)
        state["tool_results"].append({"tool": "verify_patient_identity", "result": vr})
        if vr.get("success") and vr.get("patient_user_id"):
            state["verified_patient_user_id"] = str(vr["patient_user_id"])

    if wants_cancel:
        cs = graph_state_to_chat_state(state)
        cancelled = await get_workflow_tools().cancel_appointment(cs)
        state["tool_results"].append({"tool": "cancel_appointment", "result": cancelled})
    elif wants_book:
        cs = graph_state_to_chat_state(state)
        booked = await get_workflow_tools().book_appointment(cs)
        state["tool_results"].append({"tool": "book_appointment", "result": booked})

    if wants_list:
        cs = graph_state_to_chat_state(state)
        listed = await get_workflow_tools().list_user_appointments(cs)
        state["tool_results"].append({"tool": "list_appointments", "result": listed})

    if wants_slots and not wants_book and not wants_cancel:
        cs = graph_state_to_chat_state(state)
        slotted = await get_workflow_tools().list_available_slots(cs)
        state["tool_results"].append({"tool": "list_available_slots", "result": slotted})
    return state


async def handle_complaint(state: GraphState) -> GraphState:
    cs = graph_state_to_chat_state(state)
    msg = state["user_message"]
    ref = extract_ticket_reference(msg)
    wants_list = wants_complaint_ticket_list(msg)
    wants_create = wants_new_complaint_ticket(msg)

    if ref:
        one = await get_workflow_tools().get_ticket_by_reference(cs)
        state["tool_results"].append({"tool": "get_ticket_by_reference", "result": one})

    if wants_create:
        created = await get_workflow_tools().create_ticket_from_message(cs, msg)
        state["tool_results"].append({"tool": "create_ticket", "result": created})
    elif not ref or wants_list:
        listed = await get_workflow_tools().list_tickets(cs)
        state["tool_results"].append({"tool": "list_tickets", "result": listed})
    return state


async def handle_hospital_info(state: GraphState) -> GraphState:
    return state


async def handle_medical_info(state: GraphState) -> GraphState:
    return state


async def handle_general(state: GraphState) -> GraphState:
    return state


def format_tool_response(state: GraphState) -> str:
    parts: list[str] = []
    for tr in state["tool_results"]:
        tool_name = tr.get("tool", "")
        result = tr.get("result", {})
        if not isinstance(result, dict):
            continue
        um = result.get("user_message_tr")
        if isinstance(um, str) and um.strip():
            parts.append(um.strip())
            continue
        if not result.get("success"):
            parts.append(str(result.get("error", "Bilinmeyen hata")))
            continue

        if tool_name == "list_available_slots":
            slots = result.get("slots", [])
            src = result.get("source", "")
            prefix = "Müsait randevular"
            if src == "external":
                prefix += " (dış hastane bağlantısı)"
            if not slots:
                parts.append(f"{prefix}: {result.get('date', '')} için kayıt bulunamadı.")
            else:
                parts.append(f"{prefix} ({result.get('date', '')}):")
                for s in slots[:10]:
                    line = f"  • {s['doctor']} - {s['department']}: {s['start']} - {s['end']}"
                    parts.append(line)
                if len(slots) > 10:
                    parts.append(f"  ... ve {len(slots) - 10} saat daha")

        elif tool_name == "list_tickets":
            tickets = result.get("tickets", [])
            if not tickets:
                parts.append("Kayıtlı talebiniz bulunmamaktadır.")
            else:
                parts.append("Talepleriniz:")
                for t in tickets:
                    parts.append(f"  • [{t['reference']}] {t['subject']} - {t['status']}")

        elif tool_name == "list_appointments":
            appts = result.get("appointments", [])
            if not appts:
                parts.append("Kayıtlı randevunuz bulunmamaktadır.")
            else:
                parts.append("Randevularınız:")
                for a in appts[:15]:
                    parts.append(
                        f"  • {a.get('start', '')} — {a.get('doctor', 'N/A')} "
                        f"({a.get('department', 'N/A')}) [{a.get('status', '')}]"
                    )
                if len(appts) > 15:
                    parts.append(f"  ... ve {len(appts) - 15} randevu daha")

        elif tool_name == "create_ticket":
            parts.append(result.get("message", "Talep oluşturuldu."))

        elif tool_name == "book_appointment":
            um2 = result.get("user_message_tr")
            if isinstance(um2, str) and um2.strip():
                parts.append(um2.strip())
            elif result.get("success"):
                parts.append("Randevu isteği işlendi.")
            else:
                parts.append(str(result.get("error", "Randevu oluşturulamadı.")))

        elif tool_name == "cancel_appointment":
            um3 = result.get("user_message_tr")
            if isinstance(um3, str) and um3.strip():
                parts.append(um3.strip())
            elif result.get("success"):
                parts.append("İptal isteği işlendi.")
            else:
                parts.append(str(result.get("error", "İptal işlemi tamamlanamadı.")))

        else:
            parts.append(str(result))

    return "\n".join(parts) if parts else GENERAL_FALLBACK


async def generate_response(state: GraphState) -> GraphState:
    if state["safety_flag"] and state["response"]:
        return state

    state["verify_should_retry"] = False

    intent = state["intent"]
    system_prompt = SYSTEM_PROMPTS.get(intent, SYSTEM_PROMPTS["general"])
    if not (state.get("user_id") or "").strip():
        system_prompt += (
            "\n\nBu kullanıcı oturum açmadan yazıyor. Şikayet/talep oluşturma veya "
            "randevu gibi işlemlerde ad soyad ve telefon (tercihen e-posta) bilgisini iste; "
            "kullanıcı bu bilgileri sohbette veya uygulamadaki iletişim alanına girebilir. "
            "Randevu geçmişi veya yeni randevu için önce kayıtlı cep telefonunuz ve "
            "ad-soyad ile doğrulama iste; doğrulama sonrası saatleri paylaş veya müsait slota göre "
            "rezervasyon oluştur."
        )

    messages: list[Any] = [SystemMessage(content=system_prompt)]

    for msg in state["history"]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    if state.get("strict_grounding"):
        messages.append(
            SystemMessage(
                content=(
                    "Önceki yanıt kalite kontrolünden geçmedi. Bu turda yalnızca verilen "
                    "kanıt ve araç çıktılarındaki bilgileri kullan. Kanıtta olmayan somut "
                    "iddia ekleme; eksik bilgi için 'bu bilgi dosyamda yok' de ve bilgi "
                    "hattına yönlendir."
                )
            )
        )

    if (state.get("web_context") or "").strip():
        messages.append(
            SystemMessage(
                content=(
                    "Aşağıdaki metin web aramasından otomatik gelen kısa özetlerdir; "
                    "resmi hastane bilgisi değildir. Kesin tanı veya tedavi iddiası yok; "
                    "tartışmalı konularda hekime yönlendir.\n\n"
                    f"---\n{state['web_context']}\n---"
                )
            )
        )

    if state["rag_context"]:
        context_msg = (
            "Aşağıdaki blok, bu hastane için bilgi tabanından getirilen alıntılardır. "
            "Kullanıcının sorusunu öncelikle bu metne dayanarak yanıtla; metinde yoksa "
            "dürüstçe belirt ve genel yönlendirme yap. Uydurma bilgi ekleme.\n\n"
            f"---\n{state['rag_context']}\n---"
        )
        messages.append(SystemMessage(content=context_msg))

    for tr in state["tool_results"]:
        tool_name = tr.get("tool", "")
        result = tr.get("result", {})
        if not isinstance(result, dict):
            continue
        user_tr = result.get("user_message_tr")
        if isinstance(user_tr, str) and user_tr.strip():
            messages.append(
                SystemMessage(
                    content=(
                        f"Araç: {tool_name}. Kullanıcıya net ve doğru şekilde yanıt ver; "
                        f"özeti gerektiğinde kısaltabilirsin:\n{user_tr.strip()}"
                    )
                )
            )
            continue
        if result.get("success"):
            result_msg = f"Araç sonucu ({tool_name}): {result}"
            messages.append(SystemMessage(content=str(result_msg)))

    messages.append(HumanMessage(content=state["user_message"]))

    profile = merge_llm_profile(get_llm_profile(), state["llm_overrides"] or None)

    if not (profile.llm_api_key or profile.embedding_api_key):
        if state["tool_results"]:
            state["response"] = format_tool_response(state)
        else:
            state["response"] = GENERAL_FALLBACK
        return state

    llm = get_llm(profile)
    try:
        # Generate silently — do NOT stream tokens here.
        # Tokens are emitted only after quality + safety verification in output_guardrail,
        # ensuring what the user sees is always the final, verified response.
        result = await llm.ainvoke(messages)
        state["response"] = result.content.strip()
    except Exception as exc:
        log.error("llm_response_error", error=str(exc))
        state["response"] = (
            "Üzgünüm, şu anda bir teknik sorun yaşıyorum. "
            "Lütfen daha sonra tekrar deneyin veya hastane bilgi hattını arayın."
        )

    return state


async def output_guardrail(state: GraphState) -> GraphState:
    cs = graph_state_to_chat_state(state)
    cs = await output_safety_check(cs)
    new_state = chat_state_to_graph_state(cs)

    # Stream the final response only here — after quality + safety checks have both passed.
    # This guarantees the streamed tokens always match the final response the client receives.
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        writer = None

    if writer is not None:
        final_response = (new_state.get("response") or "").strip()
        if final_response:
            writer({"type": "token", "text": final_response})

    return new_state
