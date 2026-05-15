"""Lightweight tests for appointment slot listing (no DB)."""

from __future__ import annotations

import pytest
from state import ChatState

from hospitai.application.chat.tools.appointment_tools import list_available_slots_tool


@pytest.mark.asyncio
async def test_list_available_slots_requires_target_date() -> None:
    state = ChatState(user_message="randevu?", tenant_slug="demo-hospital")
    result = await list_available_slots_tool(state, target_date="")
    assert result["success"] is False
    assert result["slot_outcome"] == "date_required"
    assert "tarih" in result["user_message_tr"].lower()


@pytest.mark.asyncio
async def test_list_available_slots_rejects_past_date() -> None:
    state = ChatState(user_message="randevu", tenant_slug="demo-hospital")
    result = await list_available_slots_tool(state, target_date="2020-01-01")
    assert result["success"] is False
    assert result["slot_outcome"] == "past_date"
