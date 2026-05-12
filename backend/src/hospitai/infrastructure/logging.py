"""Configure structlog + stdlib logging."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from hospitai.infrastructure.settings import Settings


def setup_logging(settings: Settings) -> None:
    """JSON logs outside development; human-readable console in development."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.environment == "development":
        processors = [
            *shared,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
        logger_factory = structlog.PrintLoggerFactory(file=sys.stdout)
    else:
        processors = [*shared, structlog.processors.JSONRenderer()]
        logger_factory = structlog.PrintLoggerFactory(file=sys.stdout)

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=logger_factory,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
