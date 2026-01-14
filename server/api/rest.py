"""REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

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
        {"amount": pot.amount, "eligible_seats": sorted(pot.eligible_seats)} for pot in state.pots
    ]

    return TableSnapshotResponse(
        hand_id=state.hand_id,
        street=state.street.value,
        seats=seats_data,
        current_bet=state.current_bet,
        community_cards=[
            {"rank": c.rank.value, "suit": c.suit.value} for c in state.community_cards
        ],
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
    player_id: str | None = Query(None, description="Filter by player ID"),
    table_id: str | None = Query(None, description="Filter by table ID"),
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


@router.get(
    "/players/me",
    summary="Get player info",
    description="Get current player information including chips balance.",
)
async def get_player_info(player_id: str = Depends(get_current_player)):
    """Get current player information."""
    from server.api.auth import load_users_db

    users_db = load_users_db()
    username = player_id.replace("player_", "")
    user = users_db.get(username)

    if not user:
        raise HTTPException(status_code=404, detail="Player not found")

    return {
        "player_id": player_id,
        "username": user.get("username", username),
        "chips": user.get("chips", 1000),
        "avatar": user.get("avatar", "👤"),
        "last_roulette_date": user.get("last_roulette_date", None),
    }


@router.post(
    "/players/update-chips",
    summary="Update player chips",
    description="Update player chip balance by adding/subtracting an amount.",
)
async def update_player_chips(
    amount: int = Query(..., description="Chip amount to add (can be negative for losses)"),
    player_id: str = Depends(get_current_player),
):
    """Update player chips (can be negative for losses)."""
    from server.api.auth import load_users_db, save_users_db

    users_db = load_users_db()
    username = player_id.replace("player_", "")
    user = users_db.get(username)

    if not user:
        raise HTTPException(status_code=404, detail="Player not found")

    current_chips = user.get("chips", 1000)
    new_chips = max(0, current_chips + amount)
    user["chips"] = new_chips

    save_users_db(users_db)
    
    print(f"[API] Updated chips for {player_id} ({username}): {current_chips} + {amount} = {new_chips}")

    return {"player_id": player_id, "chips": new_chips}


@router.post(
    "/players/set-chips",
    summary="Set player chips",
    description="Set player chip balance to a specific amount.",
)
async def set_player_chips(
    chips: int = Query(..., ge=0, description="New chip balance"),
    player_id: str = Depends(get_current_player),
):
    """Set player chips to a specific amount."""
    from server.api.auth import load_users_db, save_users_db

    users_db = load_users_db()
    username = player_id.replace("player_", "")
    user = users_db.get(username)

    if not user:
        raise HTTPException(status_code=404, detail="Player not found")

    old_chips = user.get("chips", 1000)
    user["chips"] = chips
    save_users_db(users_db)
    
    print(f"[API] Set chips for {player_id} ({username}): {old_chips} -> {chips}")

    return {"player_id": player_id, "chips": chips}


@router.get(
    "/tables/find-or-create",
    summary="Find or create table",
    description="Find available table or create new one if all full (max 6 players per table).",
)
async def find_or_create_table(player_id: str = Depends(get_current_player)):
    """Find available table with < 6 players, or create new one."""
    manager = get_table_manager()

    # Check existing tables for availability
    for table_id in manager.list_tables():
        table_service = manager.get_table(table_id)
        state = table_service.get_state()

        # Count seated players
        seated_count = sum(1 for seat in state.seats if seat is not None)

        if seated_count < 6:
            return {"table_id": table_id, "action": "joined"}

    # All tables full, create new one
    new_table_num = len(manager.list_tables()) + 1
    new_table_id = f"table-{new_table_num}"
    manager.get_table(new_table_id)

    return {"table_id": new_table_id, "action": "created"}


@router.post(
    "/roulette/spin",
    summary="Spin roulette",
    description="Spin the daily roulette wheel for chips reward (once per day).",
)
async def spin_roulette(player_id: str = Depends(get_current_player)):
    """Spin the roulette wheel for daily reward."""
    import random
    from datetime import date

    from server.api.auth import load_users_db, save_users_db

    users_db = load_users_db()
    username = player_id.replace("player_", "")
    user = users_db.get(username)

    if not user:
        raise HTTPException(status_code=404, detail="Player not found")

    # Check if already used today
    today = date.today().isoformat()
    last_roulette_date = user.get("last_roulette_date")

    if last_roulette_date == today:
        raise HTTPException(
            status_code=400, detail="You have already spun today. Come back tomorrow!"
        )

    # Generate reward (50-500 chips)
    reward = random.randint(50, 500)

    # Update user
    current_chips = user.get("chips", 1000)
    new_chips = current_chips + reward
    user["chips"] = new_chips
    user["last_roulette_date"] = today

    save_users_db(users_db)

    # If player is currently seated at a table, sync their stack with new chips
    try:
        from server.services.table_manager import get_table_manager
        manager = get_table_manager()
        # Check all tables (typically just one table "table-1")
        for table_id in manager.list_tables():
            table_service = manager.get_table(table_id)
            state = table_service.get_state()
            # Find player's seat
            for seat in state.seats:
                if seat is not None and seat.player_id == player_id:
                    # Update stack to match new chips (add reward to current stack)
                    old_stack = seat.stack
                    new_stack = old_stack + reward
                    # Directly update the seat's stack in the state
                    # This is a special case for roulette rewards - we bypass the command system
                    updated_seats = list(state.seats)
                    seat_idx = seat.seat_id
                    updated_seats[seat_idx] = seat.model_copy(update={"stack": new_stack})
                    table_service.current_state = state.model_copy(update={"seats": updated_seats})
                    print(f"[Roulette] Synced stack for {player_id} at {table_id}: {old_stack} -> {new_stack} (reward: {reward})")
                    break
    except Exception as e:
        # If syncing fails, log but don't fail the roulette spin
        print(f"[Roulette] Warning: Could not sync stack for seated player {player_id}: {e}")
        import traceback
        traceback.print_exc()

    return {"reward": reward, "new_chips": new_chips, "last_roulette_date": today}
