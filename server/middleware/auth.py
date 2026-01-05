"""Authentication middleware for FastAPI."""

from typing import Optional

from fastapi import Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from server.services.auth import get_player_id

security = HTTPBearer(auto_error=False)


async def get_current_player(
    authorization: Optional[HTTPAuthorizationCredentials] = Header(None),
) -> str:
    """Dependency to get current authenticated player.

    Args:
        authorization: Authorization header

    Returns:
        Player ID

    Raises:
        HTTPException: If authentication fails
    """
    token = None
    if authorization:
        token = authorization.credentials
    elif authorization is None:
        # For development, allow anonymous access
        return "anonymous"
    
    player_id = get_player_id(token)
    if player_id == "anonymous" and token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return player_id

