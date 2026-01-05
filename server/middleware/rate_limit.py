"""Rate limiting middleware."""

from collections import defaultdict
from time import time
from typing import Optional

from fastapi import Request, HTTPException, status
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from server.config import settings

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Rate limit storage (in production, use Redis)
_rate_limit_storage: dict[str, list[float]] = defaultdict(list)


def get_rate_limit_key(request: Request) -> str:
    """Get rate limit key for request.

    Args:
        request: FastAPI request

    Returns:
        Rate limit key (IP address or player ID)
    """
    # Try to get player ID from auth token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        from server.services.auth import get_player_id
        player_id = get_player_id(token)
        if player_id != "anonymous":
            return f"player:{player_id}"
    
    # Fall back to IP address
    return get_remote_address(request)


def check_rate_limit(key: str, limit: int, window: int = 60) -> bool:
    """Check if request is within rate limit.

    Args:
        key: Rate limit key
        limit: Maximum requests per window
        window: Time window in seconds

    Returns:
        True if within limit, False if exceeded
    """
    if not settings.rate_limit_enabled:
        return True
    
    now = time()
    # Clean old entries
    _rate_limit_storage[key] = [t for t in _rate_limit_storage[key] if now - t < window]
    
    # Check limit
    if len(_rate_limit_storage[key]) >= limit:
        return False
    
    # Record request
    _rate_limit_storage[key].append(now)
    return True


async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware.

    Args:
        request: FastAPI request
        call_next: Next middleware handler

    Returns:
        Response
    """
    key = get_rate_limit_key(request)
    limit = settings.rate_limit_per_minute
    
    if not check_rate_limit(key, limit, window=60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {limit} requests per minute",
        )
    
    response = await call_next(request)
    return response

