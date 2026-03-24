"""FastAPI middleware for request/response logging and correlation."""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("bodhigrove.http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every HTTP request start and end with timing and status."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Log request start, execute, then log request end with duration.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware/endpoint handler.

        Returns:
            The HTTP response.
        """
        request_id = str(uuid.uuid4())[:8]
        method = request.method
        path = request.url.path

        # Bind request context for all logs within this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=method,
            path=path,
        )

        logger.info(
            "request_start",
            client=request.client.host if request.client else "unknown",
        )

        start = time.monotonic()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "request_error",
                duration_ms=duration_ms,
                exc_info=True,
            )
            raise

        duration_ms = int((time.monotonic() - start) * 1000)
        status_code = response.status_code

        log_fn = (
            logger.info
            if status_code < 400
            else (logger.warning if status_code < 500 else logger.error)
        )
        log_fn(
            "request_end",
            status=status_code,
            duration_ms=duration_ms,
        )

        response.headers["X-Request-ID"] = request_id
        return response
