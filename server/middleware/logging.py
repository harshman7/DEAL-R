"""Structured logging middleware."""

import time
import uuid
from typing import Callable

import structlog
from fastapi import Request, Response

from server.config import settings

# Configure structlog
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer() if settings.log_format == "json" else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(settings.log_level),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


async def logging_middleware(request: Request, call_next: Callable) -> Response:
    """Logging middleware for request/response.

    Args:
        request: FastAPI request
        call_next: Next middleware handler

    Returns:
        Response
    """
    # Generate request ID
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Log request
    start_time = time.time()
    logger.info(
        "request_started",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else None,
    )
    
    try:
        response = await call_next(request)
        
        # Log response
        duration = time.time() - start_time
        logger.info(
            "request_completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration * 1000,
        )
        
        # Add request ID to response header
        response.headers["X-Request-ID"] = request_id
        
        return response
    
    except Exception as e:
        # Log error
        duration = time.time() - start_time
        logger.error(
            "request_failed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            error=str(e),
            error_type=type(e).__name__,
            duration_ms=duration * 1000,
            exc_info=True,
        )
        raise

