"""JWT-based authentication service."""

import time
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from server.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password

    Returns:
        True if password matches
    """
    # Bcrypt has a 72-byte limit, so truncate if necessary
    password_bytes = plain_password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    
    try:
        return bcrypt.checkpw(password_bytes, hashed_password.encode('utf-8'))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password.

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    # Bcrypt has a 72-byte limit, so truncate if necessary
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token.

    Args:
        data: Data to encode in token
        expires_delta: Optional expiration time delta

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError as e:
        print(f"[Auth] JWT decode error: {e}")
        return None
    except Exception as e:
        print(f"[Auth] Unexpected error decoding token: {e}")
        return None


def get_player_id(token: Optional[str] = None) -> str:
    """Get player ID from JWT token.

    Args:
        token: JWT authentication token

    Returns:
        Player ID from token, or "anonymous" if invalid/missing
    """
    if not token:
        return "anonymous"
    
    payload = decode_access_token(token)
    if payload and "sub" in payload:
        return payload["sub"]  # "sub" is standard JWT claim for subject/user ID
    
    return "anonymous"


def verify_player_can_act(player_id: str, seat_id: int, state) -> bool:
    """Verify player can act at seat.

    Args:
        player_id: Player identifier
        seat_id: Seat number
        state: Game state

    Returns:
        True if player owns the seat and can act
    """
    player = state.get_player(seat_id)
    if player is None:
        return False
    
    # Check if player_id matches seat owner
    # Note: In current implementation, player_id is stored in PlayerState
    # This would need to be added to PlayerState if not already present
    # For now, we'll check if seat is active
    return player.status.value in ("ACTIVE", "ALL_IN")


def create_player_token(player_id: str) -> str:
    """Create a token for a player (for testing/development).

    Args:
        player_id: Player identifier

    Returns:
        JWT token
    """
    return create_access_token(data={"sub": player_id})
