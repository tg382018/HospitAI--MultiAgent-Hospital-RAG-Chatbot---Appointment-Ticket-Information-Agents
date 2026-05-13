"""Domain-level HTTP errors and FastAPI exception wiring."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from hospitai.api.schemas.errors import ErrorResponse

log = structlog.get_logger(__name__)


class AppError(Exception):
    """Raised for expected API failures (maps to JSON error body)."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error_payload(code: str, message: str, request: Request) -> dict[str, Any]:
    body = ErrorResponse(
        error={"code": code, "message": message, "request_id": _request_id(request)}
    )
    return jsonable_encoder(body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        log.warning("app_error", code=exc.code, message=exc.message, status=exc.status_code)
        err: dict[str, Any] = {
            "code": exc.code,
            "message": exc.message,
            "request_id": _request_id(request),
        }
        if exc.details:
            err["details"] = exc.details
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(ErrorResponse(error=err)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        code = "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(code, message, request),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        log.info("validation_error", errors=exc.errors())
        err = {
            "code": "validation_error",
            "message": "Request validation failed",
            "request_id": _request_id(request),
            "fields": exc.errors(),
        }
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(ErrorResponse(error=err)),
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        detail = getattr(exc, "detail", None)
        message = detail if isinstance(detail, str) else "Too many requests"
        log.warning("rate_limited", message=message)
        return JSONResponse(
            status_code=429,
            content=_error_payload("rate_limited", message, request),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, _exc: Exception) -> JSONResponse:
        log.exception("unhandled_error")
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                "internal_error",
                "An unexpected error occurred",
                request,
            ),
        )
