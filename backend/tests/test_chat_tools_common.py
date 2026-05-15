"""Tests for shared chat tool helpers."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from hospitai.application.chat.tools.common import today_in_turkey


def test_today_in_turkey_returns_date() -> None:
    with patch("hospitai.application.chat.tools.common.datetime") as mock_dt:
        mock_dt.now.return_value.date.return_value = date(2026, 5, 15)
        assert today_in_turkey() == date(2026, 5, 15)
