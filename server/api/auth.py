"""Authentication API endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from server.services.auth import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
security = HTTPBearer()

# Persistent storage file (JSON for simplicity)
USERS_DB_FILE = Path("users.json")


def load_users_db() -> dict[str, dict]:
    """Load users from JSON file."""
    if USERS_DB_FILE.exists():
        try:
            with open(USERS_DB_FILE) as f:
                return json.load(f)
        except Exception as e:
            print(f"[Auth] Error loading users database: {e}")
            return {}
    return {}


def save_users_db(users_db: dict[str, dict]) -> None:
    """Save users to JSON file."""
    try:
        with open(USERS_DB_FILE, "w") as f:
            json.dump(users_db, f, indent=2)
    except Exception as e:
        print(f"[Auth] Error saving users database: {e}")


# Load users on startup
users_db: dict[str, dict] = load_users_db()
if users_db:
    print(f"[Auth] Loaded {len(users_db)} users from database")


class RegisterRequest(BaseModel):
    """Registration request."""

    username: str
    email: str  # Email validation can be added later
    password: str


class LoginRequest(BaseModel):
    """Login request."""

    username: str
    password: str


class AuthResponse(BaseModel):
    """Authentication response."""

    access_token: str
    token_type: str = "bearer"
    player_id: str
    username: str


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """Register a new player account."""
    # Validate password length
    if len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 6 characters"
        )

    if len(request.password) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password cannot be longer than 72 characters",
        )

    # Load current users to check for duplicates
    current_users = load_users_db()
    if request.username in current_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )

    # Create user
    hashed_password = get_password_hash(request.password)
    print(
        f"[Auth] Registering user '{request.username}' with hashed password: {hashed_password[:20]}..."
    )
    current_users[request.username] = {
        "username": request.username,
        "email": request.email,
        "hashed_password": hashed_password,
        "chips": 1000,  # Default starting chips
        "avatar": "👤",  # Default avatar
        "last_roulette_date": None,  # Track daily roulette
    }
    save_users_db(current_users)
    # Update global users_db
    users_db.clear()
    users_db.update(current_users)
    print(
        f"[Auth] User '{request.username}' registered successfully. Total users: {len(current_users)}"
    )

    # Generate token
    player_id = f"player_{request.username}"
    token = create_access_token(data={"sub": player_id, "username": request.username})

    return AuthResponse(access_token=token, player_id=player_id, username=request.username)


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Login with username and password."""
    # Validate password length (bcrypt limit)
    if len(request.password) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password cannot be longer than 72 characters",
        )

    # Load current users (in case file was modified)
    current_users = load_users_db()
    # Update global users_db
    users_db.clear()
    users_db.update(current_users)

    user = current_users.get(request.username)
    if not user:
        print(f"[Auth] Login failed: user '{request.username}' not found in database")
        print(f"[Auth] Available users: {list(current_users.keys())}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )

    print(f"[Auth] Verifying password for user '{request.username}'")
    password_valid = verify_password(request.password, user["hashed_password"])
    if not password_valid:
        print(f"[Auth] Login failed: password verification failed for user '{request.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )

    print(f"[Auth] Login successful for user '{request.username}'")
    # Generate token
    player_id = f"player_{request.username}"
    token = create_access_token(data={"sub": player_id, "username": request.username})

    return AuthResponse(access_token=token, player_id=player_id, username=request.username)


@router.get("/me")
async def get_current_user(token: str = Depends(security)):
    """Get current authenticated user."""
    payload = decode_access_token(token.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    username = payload.get("username", "unknown")
    player_id = payload.get("sub", "unknown")

    return {"player_id": player_id, "username": username}
