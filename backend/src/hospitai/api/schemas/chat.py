"""Pydantic schemas for the chat API."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Single message in conversation history."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    """POST /chat request body."""
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    conversation_id: uuid.UUID | None = Field(
        None,
        description="Existing conversation ID (omit to start new).",
    )


class ChatResponse(BaseModel):
    """POST /chat response body."""
    conversation_id: uuid.UUID
    message: str = Field(..., description="Assistant reply")
    intent: str = Field(..., description="Classified intent")
    sources: list[str] = Field(default_factory=list, description="RAG source documents")
    rag_used: bool = Field(
        default=False,
        description="True when the reply used tenant knowledge retrieval.",
    )
    escalated: bool = Field(
        default=False,
        description="True when the input triggered emergency escalation (112).",
    )
    safety_flag: bool = Field(default=False)
    safety_reason: str = Field(default="")