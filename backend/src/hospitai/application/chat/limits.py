"""Chat conversation length and rate limiting."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hospitai.infrastructure.db.models.conversation import ConversationMessage

_LIMIT_REACHED_TR = (
    "Bu konuşma sınırına ulaşıldı. Yeni bir konuşma başlatarak yardımcı olmaya devam edebilirim."
)


async def count_conversation_messages(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> int:
    stmt = select(func.count()).where(
        ConversationMessage.conversation_id == conversation_id,
        ConversationMessage.tenant_id == tenant_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def check_conversation_limit(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    tenant_id: uuid.UUID,
    max_messages: int,
) -> str | None:
    """Return a user-facing error message if the conversation is over the limit, else None."""
    if max_messages <= 0:
        return None
    count = await count_conversation_messages(
        session,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
    )
    if count >= max_messages:
        return _LIMIT_REACHED_TR
    return None
