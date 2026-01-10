"""Authentication middleware for FastAPI."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from server.services.auth import get_player_id

security = HTTPBearer(auto_error=False)


async def get_current_player(
    request: Request,
    authorization: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """Dependency to get current authenticated player.

    Args:
        request: FastAPI request object
        authorization: Authorization credentials from HTTPBearer (can be None)

    Returns:
        Player ID

    Raises:
        HTTPException: If authentication fails
    """
    token = None

    # Try to get token from HTTPBearer first
    if authorization:
        token = authorization.credentials
    else:
        # Fallback: try to get from Authorization header directly
        auth_header = request.headers.get("Authorization", "")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "", 1)

    # If no token provided, allow anonymous access (for development)
    if not token:
        return "anonymous"

    # Validate token
    player_id = get_player_id(token)
    if player_id == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return player_id
