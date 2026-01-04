"""REST API endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException

from engine.domain.state import GameState
from server.api.schemas import TableSnapshotResponse
from server.persistence.event_store import EventStore
from server.services.table_service import TableService

router = APIRouter(prefix="/api/v1", tags=["poker"])


def get_table_service() -> TableService:
    """Get table service instance (dependency injection stub)."""
    # In real implementation, use FastAPI Depends with database connection
    from server.persistence.event_store import EventStore

    # Use SQLite for now (can be swapped for Postgres)
    event_store = EventStore("sqlite:///./poker.db")
    return TableService(event_store)


@router.get("/tables/{table_id}/snapshot", response_model=TableSnapshotResponse)
async def get_table_snapshot(table_id: str):
    """Get current table snapshot."""
    service = get_table_service()
    state = service.get_state()

    # Convert to response format
    seats_data = []
    for seat in state.seats:
        if seat is None:
            seats_data.append(None)
        else:
            seats_data.append(seat.model_dump_public())

    pots_data = [
        {"amount": pot.amount, "eligible_seats": sorted(pot.eligible_seats)}
        for pot in state.pots
    ]

    return TableSnapshotResponse(
        hand_id=state.hand_id,
        street=state.street.value,
        seats=seats_data,
        current_bet=state.current_bet,
        community_cards=[{"rank": c.rank.value, "suit": c.suit.value} for c in state.community_cards],
        pots=pots_data,
    )


@router.get("/hands/{hand_id}/events")
async def get_hand_events(hand_id: str, from_version: int = 0):
    """Get events for a hand."""
    service = get_table_service()
    event_store = service.event_store
    events = event_store.get_events(hand_id, from_version)

    return {
        "hand_id": hand_id,
        "events": [
            {
                "version": i + from_version + 1,
                "event_type": type(e).__name__,
                "event_data": e.__dict__,
                "timestamp": e.timestamp,
            }
            for i, e in enumerate(events)
        ],
    }

