"""Attach X-Request-ID and structlog context."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        header_rid = request.headers.get("X-Request-ID")
        rid = header_rid or str(uuid.uuid4())
        request.state.request_id = rid
        structlog.contextvars.bind_contextvars(request_id=rid)
        started = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
            duration_ms = (time.perf_counter() - started) * 1000.0
            status = response.status_code if response is not None else 500
            structlog.get_logger(__name__).info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=status,
                duration_ms=round(duration_ms, 2),
            )
            if response is not None:
                response.headers["X-Request-ID"] = rid
