"""Pydantic schemas for API requests and responses."""

from typing import Annotated, Any

from pydantic import BaseModel, Field

SeatIndex = Annotated[int, Field(ge=0, le=9, description="Seat number")]


class ErrorResponse(BaseModel):
    """Error response schema."""

    error: str = Field(description="Error message")
    detail: str | None = Field(default=None, description="Detailed error information")
    request_id: str | None = Field(default=None, description="Request ID for tracking")


class SitDownRequest(BaseModel):
    """Request to sit down at a table."""

    seat_id: SeatIndex
    stack: int = Field(gt=0, description="Starting chip stack")
    player_id: str = Field(description="Unique player identifier")


class StandUpRequest(BaseModel):
    """Request to stand up from a table."""

    seat_id: SeatIndex


class ActRequest(BaseModel):
    """Request for a player action."""

    seat_id: SeatIndex
    action_type: str = Field(description="Action type: FOLD, CHECK, CALL, BET, RAISE")
    amount: int | None = Field(default=None, ge=0, description="Amount for BET/RAISE")
    idempotency_key: str = Field(description="Unique command identifier")
    expected_version: int = Field(
        ge=0, description="Expected current version for optimistic locking"
    )


class StartHandRequest(BaseModel):
    """Request to start a new hand."""

    hand_id: str = Field(description="Unique hand identifier")
    seed_commit: str = Field(description="Committed seed hash")


class TableSnapshotResponse(BaseModel):
    """Response with table snapshot."""

    hand_id: str | None = None
    street: str
    seats: list[dict[str, Any] | None]
    current_bet: int
    community_cards: list[dict]
    pots: list[dict]


class EventResponse(BaseModel):
    """Response with event data."""

    version: int
    event_type: str
    event_data: dict
    timestamp: float
