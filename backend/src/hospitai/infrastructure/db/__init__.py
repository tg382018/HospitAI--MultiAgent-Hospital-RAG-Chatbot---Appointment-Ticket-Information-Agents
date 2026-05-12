"""Database package."""

from __future__ import annotations

import hospitai.infrastructure.db.models  # noqa: F401  # register metadata
from hospitai.infrastructure.db.base import Base, TenantScopedMixin, TimestampMixin

__all__ = ["Base", "TenantScopedMixin", "TimestampMixin"]
