"""REST API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from engine.domain.state import GameState
from server.api.schemas import ErrorResponse, TableSnapshotResponse
from server.middleware.auth import get_current_player
from server.persistence.event_store import EventStore
from server.services.analytics import AnalyticsService
from server.services.hand_history import HandHistoryService
from server.services.table_manager import TableManager
from server.services.table_service import TableService

router = APIRouter(prefix="/api/v1", tags=["poker"])


# Global table manager instance (shared across all requests)
_global_table_manager = None

def get_event_store() -> EventStore:
    """Get event store instance."""
    from server.config import settings
    return EventStore(settings.database_url)


def get_table_manager() -> TableManager:
    """Get table manager instance (singleton)."""
    global _global_table_manager
    if _global_table_manager is None:
        _global_table_manager = TableManager(get_event_store())
    return _global_table_manager


def get_table_service(table_id: str) -> TableService:
    """Get table service instance for a specific table."""
    manager = get_table_manager()
    return manager.get_table(table_id)


@router.get(
    "/tables/{table_id}/snapshot",
    response_model=TableSnapshotResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get table snapshot",
    description="Retrieve the current state of a poker table including seats, pots, and community cards.",
)
async def get_table_snapshot(
    table_id: str,  # Path parameter
    player_id: str = Depends(get_current_player),
):
    """Get current table snapshot."""
    service = get_table_service(table_id)
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


@router.get(
    "/hands/{hand_id}/events",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get hand events",
    description="Retrieve the event log for a specific hand, optionally starting from a specific version.",
)
async def get_hand_events(
    hand_id: str,  # Path parameter
    from_version: int = Query(0, ge=0, description="Starting version (inclusive)"),
    player_id: str = Depends(get_current_player),
):
    """Get events for a hand."""
    event_store = get_event_store()
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


@router.get("/tables", summary="List tables", description="List all active tables")
async def list_tables(player_id: str = Depends(get_current_player)):
    """List all active tables."""
    manager = get_table_manager()
    return {"tables": manager.list_tables()}


@router.get(
    "/hands",
    summary="Search hands",
    description="Search for hands matching criteria",
)
async def search_hands(
    player_id: Optional[str] = Query(None, description="Filter by player ID"),
    table_id: Optional[str] = Query(None, description="Filter by table ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Result offset"),
    current_player: str = Depends(get_current_player),
):
    """Search for hands."""
    event_store = get_event_store()
    hand_history = HandHistoryService(event_store)
    hands = hand_history.search_hands(
        player_id=player_id, table_id=table_id, limit=limit, offset=offset
    )
    return {"hands": hands, "count": len(hands)}


@router.get(
    "/players/{player_id}/stats",
    summary="Get player statistics",
    description="Get statistics for a specific player",
)
async def get_player_stats(
    player_id: str,  # Path parameter
    current_player: str = Depends(get_current_player),
):
    """Get player statistics."""
    event_store = get_event_store()
    analytics = AnalyticsService(event_store)
    return analytics.get_player_stats(player_id)


@router.get(
    "/tables/{table_id}/stats",
    summary="Get table statistics",
    description="Get statistics for a specific table",
)
async def get_table_stats(
    table_id: str,  # Path parameter
    current_player: str = Depends(get_current_player),
):
    """Get table statistics."""
    event_store = get_event_store()
    analytics = AnalyticsService(event_store)
    return analytics.get_table_stats(table_id)


@router.get(
    "/hands/{hand_id}/summary",
    summary="Get hand summary",
    description="Get summary statistics for a specific hand",
)
async def get_hand_summary(
    hand_id: str,  # Path parameter
    current_player: str = Depends(get_current_player),
):
    """Get hand summary."""
    event_store = get_event_store()
    analytics = AnalyticsService(event_store)
    return analytics.get_hand_summary(hand_id)

