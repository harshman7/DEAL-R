"""WebSocket API for real-time game updates."""

import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from engine.domain.commands import Act, ActionType, Command, SitDown, StandUp, StartHand
from engine.domain.state import GameState
from server.api.schemas import ActRequest, SitDownRequest, StandUpRequest, StartHandRequest
from server.services.table_manager import TableManager
from server.services.table_service import TableService

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for a table."""

    def __init__(self) -> None:
        """Initialize connection manager."""
        self.active_connections: dict[str, set[WebSocket]] = {}  # table_id -> set of connections
        self.connection_player_ids: dict[WebSocket, str] = {}  # websocket -> player_id

    async def connect(self, websocket: WebSocket, table_id: str, player_id: str = "anonymous"):
        """Accept a WebSocket connection."""
        await websocket.accept()
        if table_id not in self.active_connections:
            self.active_connections[table_id] = set()
        self.active_connections[table_id].add(websocket)
        self.connection_player_ids[websocket] = player_id

    def disconnect(self, websocket: WebSocket, table_id: str):
        """Remove a WebSocket connection."""
        if table_id in self.active_connections:
            self.active_connections[table_id].discard(websocket)
        if websocket in self.connection_player_ids:
            del self.connection_player_ids[websocket]

    async def broadcast(self, table_id: str, state: GameState, exclude: WebSocket | None = None):
        """Broadcast state message to all connections on a table, customizing for each player.

        Args:
            table_id: Table identifier
            state: GameState to broadcast
            exclude: Optional WebSocket connection to exclude from broadcast
        """
        if table_id not in self.active_connections:
            print(f"[WS] No active connections for table {table_id}")
            return

        total_connections = len(self.active_connections[table_id])
        disconnected = set()

        # Get current version from the service
        # get_table_service is defined in this module, so we can call it directly
        service = get_table_service(table_id)
        event_stream_id = service.hand_id or f"table-{table_id}"
        current_version = service.event_store.get_current_version(event_stream_id)
        sent_count = 0

        for connection in self.active_connections[table_id]:
            # Skip excluded connection
            if exclude and connection == exclude:
                print("[WS] Skipping excluded connection")
                continue

            # Get player_id for this connection
            player_id = self.connection_player_ids.get(connection, "anonymous")

            # Serialize seats, including hole_cards for this player only
            serialized_seats: list[dict[str, Any] | None] = []
            for seat in state.seats:
                if seat is None:
                    serialized_seats.append(None)
                else:
                    seat_data = seat.model_dump_public()
                    # SIMPLE: Always include hole_cards if they exist (for debugging - remove in production)
                    # In production, only include if seat.player_id == player_id
                    if seat.hole_cards:
                        seat_data["hole_cards"] = [
                            {"rank": c.rank.value, "suit": c.suit.value} for c in seat.hole_cards
                        ]
                        print(
                            f"[WS] ✓ Including hole_cards for seat {seat.seat_id} (player_id={seat.player_id}, connection_player_id={player_id}): {seat_data['hole_cards']}"
                        )
                    serialized_seats.append(seat_data)

            # Create personalized message for this connection
            personalized_message = {
                "type": "state",
                "version": current_version,
                "data": {
                    "hand_id": state.hand_id,
                    "street": state.street.value,
                    "current_bet": state.current_bet,
                    "to_act_seat": state.to_act_seat,
                    "min_raise": state.min_raise,
                    "big_blind": state.big_blind,
                    "small_blind": state.small_blind,
                    "button_seat": state.button_seat,
                    "sb_seat": state.sb_seat,
                    "bb_seat": state.bb_seat,
                    "seats": serialized_seats,
                    "community_cards": [
                        {"rank": c.rank.value, "suit": c.suit.value} for c in state.community_cards
                    ],
                    "pots": [
                        {"amount": pot.amount, "eligible_seats": sorted(pot.eligible_seats)}
                        for pot in state.pots
                    ],
                    "last_hand_results": state.last_hand_results,
                },
            }

            try:
                await connection.send_json(personalized_message)
                sent_count += 1
            except Exception as e:
                print(f"[WS] Error sending to connection: {e}")
                disconnected.add(connection)

        # Remove disconnected connections
        for conn in disconnected:
            self.disconnect(conn, table_id)

        print(
            f"[WS] Broadcast complete: sent to {sent_count} of {total_connections} connection(s) on table {table_id}"
        )


# Global connection manager
manager = ConnectionManager()


# Global table manager to share table instances across connections
_table_manager = None


def get_table_manager() -> TableManager:
    """Get global table manager instance."""
    global _table_manager
    if _table_manager is None:
        from server.persistence.event_store import EventStore
        from server.services.table_manager import TableManager

        event_store = EventStore("sqlite:///./poker.db")
        _table_manager = TableManager(event_store)
    return _table_manager


def get_table_service(table_id: str = "default") -> TableService:
    """Get table service instance (shared across connections)."""
    manager = get_table_manager()
    return manager.get_table(table_id)


@router.websocket("/ws/tables/{table_id}")
async def websocket_endpoint(websocket: WebSocket, table_id: str):
    """WebSocket endpoint for table updates."""
    # Get player ID from query params or token (WebSocket doesn't support headers easily)
    # For now, allow anonymous access but validate in production
    player_id = "anonymous"
    try:
        token = websocket.query_params.get("token")
        if token:
            from server.services.auth import decode_access_token

            payload = decode_access_token(token)
            if payload and "sub" in payload:
                player_id = payload["sub"]
                print(f"[WS] Extracted player_id from token: {player_id}")
            else:
                print(f"[WS] Token payload missing 'sub': {payload}")
        else:
            print("[WS] No token in query params")
    except Exception as e:
        import traceback

        print(f"[WS] Error extracting player_id: {e}")
        traceback.print_exc()
        pass

    await manager.connect(websocket, table_id, player_id)

    service = get_table_service(table_id)

    try:
        # Send initial state with full table data
        # Force reload to get latest state from events (will re-deal cards if hand started)
        service.current_state = None  # Invalidate cache
        state = service.get_state()

        # Build pots from committed chips if hand is active and pots are empty
        if state.street.value not in ("WAITING", "COMPLETE"):
            from engine.rules.sidepots import build_side_pots

            # Build pots from player commitments
            pots = build_side_pots(state)
            if pots:
                state = state.model_copy(update={"pots": pots})
                service.current_state = state

        # Get current version
        event_stream_id = service.hand_id or f"table-{service.table_id}"
        current_version = service.event_store.get_current_version(event_stream_id)
        seated_count = sum(1 for seat in state.seats if seat is not None)

        # If hand has completed (street is WAITING with last_hand_results), ensure chips are synced
        # This handles the case where a player reconnects after a hand ends
        if state.street.value == "WAITING" and state.last_hand_results:
            print("[WS] Initial connection: Hand has completed, syncing chips for seated players")
            from server.api.auth import load_users_db, save_users_db

            for seat in state.seats:
                if seat is not None and seat.player_id and seat.stack is not None:
                    try:
                        users_db = load_users_db()
                        username = seat.player_id.replace("player_", "")
                        user = users_db.get(username)

                        if user:
                            old_chips = user.get("chips", 1000)
                            if old_chips != seat.stack:
                                user["chips"] = seat.stack
                                save_users_db(users_db)
                                print(
                                    f"[WS] Synced chips for {seat.player_id} ({username}): {old_chips} -> {seat.stack}"
                                )
                    except Exception as e:
                        print(
                            f"[WS] Error syncing chips for {seat.player_id} on initial connect: {e}"
                        )

        print(
            f"[WS] Sending initial state to {player_id} on table {table_id}: {seated_count} players, version {current_version}"
        )

        # Serialize seats, including hole_cards for current player only
        serialized_seats: list[dict[str, Any] | None] = []
        for seat in state.seats:
            if seat is None:
                serialized_seats.append(None)
            else:
                seat_data = seat.model_dump_public()
                # SIMPLE: Always include hole_cards if they exist (for debugging)
                if seat.hole_cards:
                    seat_data["hole_cards"] = [
                        {"rank": c.rank.value, "suit": c.suit.value} for c in seat.hole_cards
                    ]
                    print(
                        f"[WS] Initial state: Including hole_cards for seat {seat.seat_id} (player_id={seat.player_id}): {seat_data['hole_cards']}"
                    )
                serialized_seats.append(seat_data)

        initial_state_message = {
            "type": "state",
            "version": current_version,
            "data": {
                "hand_id": state.hand_id,
                "street": state.street.value,
                "current_bet": state.current_bet,
                "to_act_seat": state.to_act_seat,
                "min_raise": state.min_raise,
                "small_blind": state.small_blind,
                "big_blind": state.big_blind,
                "button_seat": state.button_seat,
                "sb_seat": state.sb_seat,
                "bb_seat": state.bb_seat,
                "seats": serialized_seats,
                "community_cards": [
                    {"rank": c.rank.value, "suit": c.suit.value} for c in state.community_cards
                ],
                "pots": [
                    {"amount": pot.amount, "eligible_seats": sorted(pot.eligible_seats)}
                    for pot in state.pots
                ],
                "last_hand_results": state.last_hand_results,
            },
        }

        await websocket.send_json(initial_state_message)

        # Broadcast state to all other connections so they see the new connection
        # (This ensures all clients have the latest state when someone new joins)
        other_connections_count = (
            len(manager.active_connections.get(table_id, set())) - 1
        )  # Exclude self
        if other_connections_count > 0:
            print(
                f"[WS] Broadcasting state to {other_connections_count} other connection(s) on table {table_id}"
            )
            await manager.broadcast(
                table_id,
                state,
                exclude=websocket,  # Don't send to the new connection (already sent)
            )
        else:
            print(f"[WS] No other connections to broadcast to on table {table_id}")

        while True:
            # Receive command
            data = await websocket.receive_json()

            command_type = data.get("type")
            command: Command | None = None
            cmd_idempotency_key = ""
            cmd_expected_version = 0
            standing_player_stack: int | None = None
            standing_player_id: str | None = None
            stand_up_seat_id: int | None = None

            if command_type == "sit_down":
                sit_req = SitDownRequest(**data["data"])
                print(
                    f"[WS] Processing sit_down command: player={sit_req.player_id}, seat={sit_req.seat_id}, stack={sit_req.stack}"
                )

                # Check table capacity before processing (max 6 players)
                current_state = service.get_state()
                seated_count = sum(1 for seat in current_state.seats if seat is not None)
                if seated_count >= 6:
                    error_msg = "Table is full (max 6 players). Please join a different table."
                    print(f"[WS] Command failed: {error_msg}")
                    await websocket.send_json({"type": "error", "message": error_msg})
                    continue

                cmd_idempotency_key = data.get("idempotency_key", f"sit-{time.time()}")
                cmd_expected_version = int(data.get("expected_version", 0))
                command = SitDown(
                    idempotency_key=cmd_idempotency_key,
                    timestamp=time.time(),
                    seat_id=sit_req.seat_id,
                    stack=sit_req.stack,
                    player_id=sit_req.player_id,
                )

            elif command_type == "act":
                action_data = data["data"]
                act_idempotency_key = (
                    data.get("idempotency_key")
                    or action_data.get("idempotency_key")
                    or f"act-{time.time()}"
                )
                act_expected_version = (
                    data.get("expected_version") or action_data.get("expected_version") or 0
                )

                act_req = ActRequest(
                    seat_id=action_data["seat_id"],
                    action_type=action_data["action_type"],
                    amount=action_data.get("amount"),
                    idempotency_key=act_idempotency_key,
                    expected_version=int(act_expected_version),
                )
                cmd_idempotency_key = act_idempotency_key
                cmd_expected_version = int(act_expected_version)
                command = Act(
                    idempotency_key=act_idempotency_key,
                    timestamp=time.time(),
                    seat_id=act_req.seat_id,
                    action_type=ActionType(act_req.action_type),
                    amount=act_req.amount,
                )

            elif command_type == "start_hand":
                start_req = StartHandRequest(**data["data"])
                print(
                    f"[WS] Processing start_hand command: hand_id={start_req.hand_id}, seed_commit={start_req.seed_commit[:20]}..."
                )
                cmd_idempotency_key = data.get("idempotency_key", f"start-{time.time()}")
                cmd_expected_version = int(data.get("expected_version", 0))
                command = StartHand(
                    idempotency_key=cmd_idempotency_key,
                    timestamp=time.time(),
                    hand_id=start_req.hand_id,
                    seed_commit=start_req.seed_commit,
                )

            elif command_type == "stand_up":
                stand_req = StandUpRequest(**data["data"])
                print(
                    f"[WS] Processing stand_up command: seat={stand_req.seat_id}, player={player_id}"
                )
                prev_state = service.get_state()
                standing_player_seat = (
                    prev_state.seats[stand_req.seat_id]
                    if stand_req.seat_id < len(prev_state.seats)
                    else None
                )
                standing_player_stack = standing_player_seat.stack if standing_player_seat else None
                standing_player_id = (
                    standing_player_seat.player_id if standing_player_seat else None
                )
                stand_up_seat_id = stand_req.seat_id

                cmd_idempotency_key = data.get("idempotency_key", f"stand-{time.time()}")
                cmd_expected_version = int(data.get("expected_version", 0))
                command = StandUp(
                    idempotency_key=cmd_idempotency_key,
                    timestamp=time.time(),
                    seat_id=stand_req.seat_id,
                )

            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown command: {command_type}"}
                )
                continue

            # Process command
            try:
                assert command is not None
                print(
                    f"[WS] Processing command {command_type}, expected_version={cmd_expected_version}"
                )
                new_state, events, new_version = service.process_command(
                    command, cmd_idempotency_key, cmd_expected_version
                )
                print(
                    f"[WS] Command processed successfully: {len(events)} events, version={new_version}"
                )

                # Send success response
                await websocket.send_json(
                    {
                        "type": "command_accepted",
                        "idempotency_key": data.get("idempotency_key"),
                        "new_version": new_version,
                    }
                )

                # Events are included in state broadcast below
                # No need to broadcast individual events

                # Use the new_state directly (already has cards dealt from process_command)
                updated_state = new_state

                # Build pots from committed chips if hand is active and pots are empty
                if updated_state.street.value not in ("WAITING", "COMPLETE"):
                    from engine.rules.sidepots import build_side_pots

                    # Build pots from player commitments
                    pots = build_side_pots(updated_state)
                    if pots:
                        updated_state = updated_state.model_copy(update={"pots": pots})

                # Update cache to avoid unnecessary reloads
                service.current_state = updated_state

                # Check if player stood up - persist their chips
                from engine.domain.events import PlayerStoodUp

                player_stood_up = any(isinstance(e, PlayerStoodUp) for e in events)
                if player_stood_up and standing_player_id and standing_player_stack is not None:
                    seat_disp = stand_up_seat_id if stand_up_seat_id is not None else "?"
                    print(
                        f"[WS] Player stood up, updating chips for {standing_player_id} (seat {seat_disp}): {standing_player_stack}"
                    )
                    try:
                        from server.api.auth import load_users_db, save_users_db

                        users_db = load_users_db()
                        username = standing_player_id.replace("player_", "")
                        user = users_db.get(username)

                        if user:
                            old_chips = user.get("chips", 1000)
                            user["chips"] = standing_player_stack
                            save_users_db(users_db)
                            print(
                                f"[WS] Updated chips for {standing_player_id} ({username}) after stand_up: {old_chips} -> {standing_player_stack}"
                            )
                        else:
                            print(f"[WS] Warning: User {username} not found in database")
                    except Exception as e:
                        print(
                            f"[WS] Error updating chips for {standing_player_id} after stand_up: {e}"
                        )
                        import traceback

                        traceback.print_exc()

                # Check if hand just ended (HandEnded event in events or street is WAITING with last_hand_results)
                # If so, update player chips in their accounts
                from engine.domain.events import HandEnded

                hand_ended = any(isinstance(e, HandEnded) for e in events)
                if hand_ended or (
                    updated_state.street.value == "WAITING" and updated_state.last_hand_results
                ):
                    print("[WS] Hand ended, updating player chips for all seated players")
                    # Update chips for all seated players
                    for seat in updated_state.seats:
                        if seat is not None and seat.player_id and seat.stack is not None:
                            try:
                                # Import here to avoid circular imports
                                from server.api.auth import load_users_db, save_users_db

                                users_db = load_users_db()
                                username = seat.player_id.replace("player_", "")
                                user = users_db.get(username)

                                if user:
                                    old_chips = user.get("chips", 1000)
                                    user["chips"] = seat.stack
                                    save_users_db(users_db)
                                    print(
                                        f"[WS] Updated chips for {seat.player_id} ({username}): {old_chips} -> {seat.stack}"
                                    )
                                else:
                                    print(f"[WS] Warning: User {username} not found in database")
                            except Exception as e:
                                print(f"[WS] Error updating chips for {seat.player_id}: {e}")
                                import traceback

                                traceback.print_exc()

                # Get current version for state message
                event_stream_id = service.hand_id or f"table-{service.table_id}"
                current_version = new_version  # Use the version returned from process_command

                # Count seated players for logging
                seated_count = sum(1 for seat in updated_state.seats if seat is not None)
                seated_player_ids = [
                    seat.player_id
                    for seat in updated_state.seats
                    if seat is not None and seat.player_id
                ]

                # Serialize seats with hole_cards for the sender (similar to broadcast logic)
                sender_player_id = manager.connection_player_ids.get(websocket, "anonymous")
                reply_seats: list[dict[str, Any] | None] = []
                for seat in updated_state.seats:
                    if seat is None:
                        reply_seats.append(None)
                    else:
                        seat_data = seat.model_dump_public()
                        # Include hole_cards if they exist (for debugging, show to all; in production, filter by player_id)
                        if seat.hole_cards:
                            seat_data["hole_cards"] = [
                                {"rank": c.rank.value, "suit": c.suit.value}
                                for c in seat.hole_cards
                            ]
                            print(
                                f"[WS] ✓ State message: Including hole_cards for seat {seat.seat_id} (player_id={seat.player_id}, sender_player_id={sender_player_id}): {seat_data['hole_cards']}"
                            )
                        reply_seats.append(seat_data)

                state_message = {
                    "type": "state",
                    "version": current_version,
                    "data": {
                        "hand_id": updated_state.hand_id,
                        "street": updated_state.street.value,
                        "current_bet": updated_state.current_bet,
                        "to_act_seat": updated_state.to_act_seat,
                        "min_raise": updated_state.min_raise,
                        "small_blind": updated_state.small_blind,
                        "big_blind": updated_state.big_blind,
                        "button_seat": updated_state.button_seat,
                        "sb_seat": updated_state.sb_seat,
                        "bb_seat": updated_state.bb_seat,
                        "seats": reply_seats,
                        "community_cards": [
                            {"rank": c.rank.value, "suit": c.suit.value}
                            for c in updated_state.community_cards
                        ],
                        "pots": [
                            {"amount": pot.amount, "eligible_seats": sorted(pot.eligible_seats)}
                            for pot in updated_state.pots
                        ],
                        "last_hand_results": updated_state.last_hand_results,
                    },
                }

                # Broadcast to all other connections (exclude sender - they already got command_accepted and will get state next)
                print(
                    f"[WS] Broadcasting state to table {table_id}: {seated_count} players ({seated_player_ids}), version {current_version}, street={updated_state.street.value}, to_act_seat={updated_state.to_act_seat}"
                )
                # Send state to sender first (with hole_cards included)
                await websocket.send_json(state_message)
                # Then broadcast to other connections (also includes hole_cards via broadcast method)
                await manager.broadcast(table_id, updated_state, exclude=websocket)

            except ValueError as e:
                error_msg = str(e)
                print(f"[WS] Command failed: {error_msg}")
                await websocket.send_json({"type": "error", "message": error_msg})
            except Exception as e:
                import traceback

                error_msg = f"Unexpected error: {str(e)}"
                print(f"[WS] Unexpected error processing command: {e}")
                traceback.print_exc()
                await websocket.send_json({"type": "error", "message": error_msg})

    except WebSocketDisconnect:
        manager.disconnect(websocket, table_id)
