"""Authentication API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from server.config import settings
from server.services.auth import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
security = HTTPBearer()

# Simple in-memory user store (in production, use proper database)
Base = declarative_base()


class User(Base):
    """User model for authentication."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)


# In-memory storage for demo (replace with database in production)
users_db: dict[str, dict] = {}


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
            status_code=status.HTTP_400_BAD_REQUEST, detail="Password cannot be longer than 72 characters"
        )
    
    if request.username in users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )

    # Create user
    hashed_password = get_password_hash(request.password)
    users_db[request.username] = {
        "username": request.username,
        "email": request.email,
        "hashed_password": hashed_password,
    }

    # Generate token
    player_id = f"player_{request.username}"
    token = create_access_token(data={"sub": player_id, "username": request.username})

    return AuthResponse(
        access_token=token, player_id=player_id, username=request.username
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Login with username and password."""
    # Validate password length (bcrypt limit)
    if len(request.password) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Password cannot be longer than 72 characters"
        )
    
    user = users_db.get(request.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )

    if not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )

    # Generate token
    player_id = f"player_{request.username}"
    token = create_access_token(data={"sub": player_id, "username": request.username})

    return AuthResponse(
        access_token=token, player_id=player_id, username=request.username
    )


@router.get("/me")
async def get_current_user(token: str = Depends(security)):
    """Get current authenticated user."""
    payload = decode_access_token(token.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    username = payload.get("username", "unknown")
    player_id = payload.get("sub", "unknown")

    return {"player_id": player_id, "username": username}

