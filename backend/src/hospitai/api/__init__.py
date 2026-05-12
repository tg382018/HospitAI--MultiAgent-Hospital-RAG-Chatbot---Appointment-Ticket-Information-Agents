"""HTTP API surface (lazy exports to avoid import cycles)."""

from __future__ import annotations

from typing import Any

__all__ = ["app", "create_app"]


def __getattr__(name: str) -> Any:
    if name in ("app", "create_app"):
        from hospitai.api import main as _main

        return getattr(_main, name)
    raise AttributeError(name)
