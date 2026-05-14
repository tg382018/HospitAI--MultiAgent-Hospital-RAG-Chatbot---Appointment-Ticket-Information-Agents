#!/usr/bin/env python3
"""demo-hospital tenant için örnek bilgi tabanı metni yükle (embedding + Chroma).

Önkoşullar: Docker (Postgres, Chroma), backend/.env (DATABASE_URL, OPENAI_API_KEY),
API ile aynı Chroma ayarları.

  cd backend && python3 scripts/seed_demo_rag.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEMO_DOC_TITLE = "Demo Hastane — Bilgi kitapçığı (otomatik)"

# RAG ve LLM için zengin, tutarlı kurumsal içerik (kısaltılmış değil; chunk’lara bölünür).
DEMO_KB_MARKDOWN = """
# Demo Hastane — Hasta bilgilendirme

## Poliklinikler ve bölümler
- **Kardiyoloji:** Kalp ve damar hastalıkları polikliniği. Hafta içi 08:30–17:30.
- **Dahiliye:** Hipertansiyon, diyabet, tiroid ve genel dahili muayene. 08:30–17:00.
- **Ortopedi:** Eklem, kırık sonrası kontroller, spor yaralanmaları. 09:00–16:30.
- **Kadın doğum:** Gebelik takibi ve jinekolojik muayene (randevu zorunlu).
- **Çocuk sağlığı:** 0–18 yaş poliklinik. Aşı programı için aile hekimliği veya randevu hattı.
- **Göz hastalıkları:** Rutin göz muayenesi ve katar glokom polikliniği.
- **Kulak burun boğaz:** Sinüzit, işitme taraması, bademcik değerlendirmesi.

## Randevu
- **Online / mobil:** Hasta portalından “Randevu al” menüsü.
- **Telefon:** 444 0 DEMO (örnek numara) — mesai saatleri içinde.
- **Yerinde:** Ana bina zemin kat hasta işleri.
- Randevuya **15 dk erken** gelin; kimlik ve varsa önceki tetkikleri yanınızda bulundurun.

## Ziyaret ve refakat
- Servis ziyaret saatleri: genelde **11:00–13:00** ve **17:00–19:00** (yoğunlukla değişebilir).
- Yataklı serviste refakat: hekim onayı ve yoğun bakım dışı servislerde kısıtlı sayıda.

## Acil servis
- **7/24** açıktır. Hayatı tehdit eden durumlarda **112**’yi arayın.
- Acilde triyaj ile önceliklendirme yapılır; acil olmayan şikayetlerde bekleme süresi uzayabilir.

## Otopark ve ulaşım
- Zemin ve -1 katta hasta/ ziyaretçi otoparkı (ücret tarifesi gişede).
- Toplu taşıma: “Demo Hastane” durağı ana cadde üzerinde 150 m.

## Geri bildirim ve şikayet
- **Hasta İlişkileri:** zemin kat danışma.
- **Dijital talep:** Portal üzerinden “Şikayet / öneri” formu; referans numarası ile takip.

## Gizlilik
- Kişisel sağlık verileri KVKK ve mevzuata uygun işlenir; üçüncü kişilerle paylaşılmaz.

## Genel uyarı (bilgilendirme)
- Bu metin demo ortamı içindir; gerçek tedavi kararı için mutlaka hekiminize danışın.
"""


async def _run() -> None:
    from hospitai_agent.llm.profile import LLMProfile, configure_llm_profile
    from hospitai_agent.rag.profile import RagInfrastructureProfile, configure_rag_profile
    from sqlalchemy import select

    from hospitai.application import rag as rag_svc
    from hospitai.infrastructure.db.models.document import Document
    from hospitai.infrastructure.db.models.tenant import Tenant
    from hospitai.infrastructure.db.session import get_engine, get_session_factory
    from hospitai.infrastructure.settings import get_settings

    settings = get_settings()
    configure_llm_profile(
        LLMProfile(
            llm_model=settings.llm_model,
            llm_api_key=settings.llm_api_key,
            llm_base_url=settings.llm_base_url,
            llm_temperature=settings.llm_temperature,
            embedding_api_key=settings.embedding_api_key,
        )
    )
    configure_rag_profile(
        RagInfrastructureProfile(
            chroma_host=settings.chroma_host,
            chroma_port=settings.chroma_port,
            chroma_collection_prefix=settings.chroma_collection_prefix,
            embedding_model=settings.embedding_model,
            embedding_api_key=settings.embedding_api_key,
            embedding_dimensions=settings.embedding_dimensions,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    )

    factory = get_session_factory()
    async with factory() as session:
        row = await session.execute(select(Tenant).where(Tenant.slug == "demo-hospital"))
        tenant = row.scalar_one_or_none()
        if tenant is None:
            raise SystemExit("demo-hospital tenant bulunamadı (migration seed çalıştı mı?)")

        dup = await session.execute(
            select(Document.id).where(
                Document.tenant_id == tenant.id,
                Document.title == DEMO_DOC_TITLE,
            )
        )
        if dup.scalar_one_or_none():
            print(f"Zaten var: {DEMO_DOC_TITLE} — atlanıyor.")
            return

        await rag_svc.ingest_document(
            session,
            tenant=tenant,
            title=DEMO_DOC_TITLE,
            source_type="faq",
            content=DEMO_KB_MARKDOWN,
        )
        await session.commit()
        print(f"Tamam: '{DEMO_DOC_TITLE}' yüklendi (embedding + Chroma).")

    await get_engine().dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
