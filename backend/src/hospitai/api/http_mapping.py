"""Map application ``DomainError`` to HTTP ``AppError``."""

from __future__ import annotations

from typing import NoReturn

from hospitai.api.errors import AppError
from hospitai.application.errors import DomainError


def raise_from_domain(exc: DomainError) -> NoReturn:
    raise AppError(exc.code, exc.message, status_code=exc.status_code) from exc
