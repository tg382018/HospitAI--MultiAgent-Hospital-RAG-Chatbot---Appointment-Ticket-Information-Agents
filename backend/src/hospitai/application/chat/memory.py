"""Conversation memory management for the chat workflow.

Loads recent conversation history from the database and formats it
for inclusion in LLM context.
"""

from __future__ import annotations

import uuid

from state import ChatState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hospitai.infrastructure.db.models.conversation import Conversation, ConversationMessage
from hospitai.infrastructure.settings import get_settings


async def load_memory(
    state: ChatState,
    session: AsyncSession,
    conversation_id: uuid.UUID | None,
    *,
    max_messages: int | None = None,
) -> ChatState:
    """Load recent conversation history into state.history."""
    if conversation_id is None:
        return state

    settings = get_settings()
    max_msgs = max_messages if max_messages is not None else settings.max_conversation_history

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(max_msgs)
    )
    result = await session.execute(stmt)
    messages = list(reversed(result.scalars().all()))

    state.history = [{"role": msg.role, "content": msg.content} for msg in messages]
    return state


async def save_message(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    content: str,
    token_count: int | None = None,
) -> ConversationMessage:
    """Persist a single message to the conversation_messages table."""
    msg = ConversationMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        role=role,
        content=content,
        token_count=token_count,
    )
    session.add(msg)
    await session.flush()
    return msg


async def get_or_create_conversation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    conversation_id: uuid.UUID | None,
) -> Conversation:
    """Fetch an existing conversation or create a new one."""
    if conversation_id is not None:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        conv = result.scalar_one_or_none()
        if conv is not None:
            return conv

    conv = Conversation(
        id=conversation_id or uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        channel="web",
    )
    session.add(conv)
    await session.flush()
    return conv
