"""TC Kimlik doğrulama ve ad-soyad eşleştirme (hasta doğrulama)."""

from __future__ import annotations

import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hospitai.infrastructure.db.models.enums import UserRole
from hospitai.infrastructure.db.models.user import User


def normalize_tc(raw: str) -> str | None:
    """11 haneli rakam dizisine indirger; geçersizse None."""
    s = re.sub(r"\D", "", (raw or "").strip())
    if len(s) != 11:
        return None
    if s[0] == "0":
        return None
    return s


def is_valid_turkish_national_id(tc: str) -> bool:
    """TC Kimlik No aritmetik kontrolleri (MVP; resmi doğrulama değildir)."""
    n = normalize_tc(tc)
    if n is None:
        return False
    d = [int(x) for x in n]
    odd = sum(d[i] for i in range(0, 9, 2))
    even = sum(d[i] for i in range(1, 9, 2))
    if (odd * 7 - even) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


def _fold_tr(s: str) -> str:
    t = (s or "").strip().lower()
    for a, b in (
        ("ı", "i"),
        ("ğ", "g"),
        ("ü", "u"),
        ("ş", "s"),
        ("ö", "o"),
        ("ç", "c"),
        ("â", "a"),
        ("î", "i"),
        ("û", "u"),
    ):
        t = t.replace(a, b)
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


def names_match(*, stated: str, stored: str | None) -> bool:
    """Kayıtlı ad-soyad ile kullanıcı ifadesi; en az iki kelime, küme eşleşmesi."""
    a = _fold_tr(stated)
    b = _fold_tr(stored or "")
    if len(a) < 3 or len(b) < 3:
        return False
    ta = {w for w in re.split(r"\s+", a) if len(w) >= 2}
    tb = {w for w in re.split(r"\s+", b) if len(w) >= 2}
    if len(ta) < 2 or len(tb) < 2:
        return False
    return tuple(sorted(ta)) == tuple(sorted(tb))


def extract_tc_from_text(text: str) -> str | None:
    for m in re.finditer(r"\b(\d{11})\b", text or ""):
        cand = m.group(1)
        if is_valid_turkish_national_id(cand):
            return cand
    return None


def extract_stated_full_name(user_message: str, guest_full_name: str) -> str:
    if (guest_full_name or "").strip():
        return guest_full_name.strip()
    text = (user_message or "").strip()
    patterns = [
        r"(?:benim\s+adım|adım\s+soyadım|adım|ismim|ben)\s+([A-Za-zÇĞİÖŞÜçğıöşüa-zı\s\.]{3,80})",
        r"(?:ad\s+soyad)\s*[:\-]\s*([A-Za-zÇĞİÖŞÜçğıöşüa-zı\s\.]{3,80})",
    ]
    tl = text.lower()
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = re.sub(r"\s+", " ", m.group(1).strip())
            # "ben randevu" gibi yanlış yakalamaları kes
            if not re.search(r"\b(randevu|talep|şikayet|tc|kimlik)\b", name.lower()):
                return name[:120]
    # "Ali Deniz" cümle başı iki kelime
    m2 = re.match(
        r"^([A-ZÇĞİÖŞÜ][a-zçğıöşü]+\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+)\b",
        text,
    )
    if m2 and "randevu" not in tl[:40]:
        return m2.group(1).strip()[:120]
    return ""


async def find_patient_by_national_id(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    national_id: str,
) -> User | None:
    nid = normalize_tc(national_id)
    if not nid:
        return None
    stmt = select(User).where(
        User.tenant_id == tenant_id,
        User.national_id == nid,
        User.role == UserRole.PATIENT,
        User.is_active.is_(True),
    )
    row = await session.execute(stmt)
    return row.scalar_one_or_none()
