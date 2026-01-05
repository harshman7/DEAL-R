"""Pydantic schemas for API requests and responses."""

from typing import Optional

from pydantic import BaseModel, Field

from engine.domain.commands import ActionType


class ErrorResponse(BaseModel):
    """Error response schema."""

    error: str = Field(description="Error message")
    detail: Optional[str] = Field(default=None, description="Detailed error information")
    request_id: Optional[str] = Field(default=None, description="Request ID for tracking")


class SitDownRequest(BaseModel):
    """Request to sit down at a table."""

    seat_id: int = Field(ge=0, le=9, description="Seat number")
    stack: int = Field(gt=0, description="Starting chip stack")
    player_id: str = Field(description="Unique player identifier")


class ActRequest(BaseModel):
    """Request for a player action."""

    seat_id: int = Field(ge=0, le=9, description="Seat number")
    action_type: str = Field(description="Action type: FOLD, CHECK, CALL, BET, RAISE")
    amount: Optional[int] = Field(default=None, ge=0, description="Amount for BET/RAISE")
    idempotency_key: str = Field(description="Unique command identifier")
    expected_version: int = Field(ge=0, description="Expected current version for optimistic locking")


class StartHandRequest(BaseModel):
    """Request to start a new hand."""

    hand_id: str = Field(description="Unique hand identifier")
    seed_commit: str = Field(description="Committed seed hash")


class TableSnapshotResponse(BaseModel):
    """Response with table snapshot."""

    hand_id: Optional[str] = None
    street: str
    seats: list[dict]
    current_bet: int
    community_cards: list[dict]
    pots: list[dict]


class EventResponse(BaseModel):
    """Response with event data."""

    version: int
    event_type: str
    event_data: dict
    timestamp: float

