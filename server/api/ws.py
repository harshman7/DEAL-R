"""WebSocket API for real-time game updates."""

import json
import time
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from engine.domain.commands import Act, ActionType, SitDown, StartHand
from engine.domain.events import DomainEvent
from server.api.schemas import ActRequest, SitDownRequest, StartHandRequest
from server.services.auth import get_player_id, verify_player_can_act
from server.services.table_service import TableService

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for a table."""

    def __init__(self):
        """Initialize connection manager."""
        self.active_connections: Dict[str, Set[WebSocket]] = {}  # table_id -> set of connections
        self.connection_player_ids: Dict[WebSocket, str] = {}  # websocket -> player_id

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

    async def broadcast(self, table_id: str, state: "GameState", exclude=None):
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
                print(f"[WS] Skipping excluded connection")
                continue
            
            # Get player_id for this connection
            player_id = self.connection_player_ids.get(connection, "anonymous")
            
            # Serialize seats, including hole_cards for this player only
            serialized_seats = []
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
                        print(f"[WS] ✓ Including hole_cards for seat {seat.seat_id} (player_id={seat.player_id}, connection_player_id={player_id}): {seat_data['hole_cards']}")
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
        
        print(f"[WS] Broadcast complete: sent to {sent_count} of {total_connections} connection(s) on table {table_id}")


# Global connection manager
manager = ConnectionManager()


# Global table manager to share table instances across connections
_table_manager = None

def get_table_manager():
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
            print(f"[WS] No token in query params")
    except Exception as e:
        import traceback
        print(f"[WS] Error extracting player_id: {e}")
        traceback.print_exc()
        pass
    
    await manager.connect(websocket, table_id, player_id)
    
    service = get_table_service(table_id)

    try:
        # Send initial state with full table data
        # Force reload to get latest state from events
        service.current_state = None  # Invalidate cache
        state = service.get_state()
        
        # Get current version
        event_stream_id = service.hand_id or f"table-{service.table_id}"
        current_version = service.event_store.get_current_version(event_stream_id)
        seated_count = sum(1 for seat in state.seats if seat is not None)
        
        print(f"[WS] Sending initial state to {player_id} on table {table_id}: {seated_count} players, version {current_version}")
        
        # Serialize seats, including hole_cards for current player only
        serialized_seats = []
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
                    print(f"[WS] Initial state: Including hole_cards for seat {seat.seat_id} (player_id={seat.player_id}): {seat_data['hole_cards']}")
                serialized_seats.append(seat_data)
        
        initial_state_message = {
            "type": "state",
            "version": current_version,
            "data": {
                "hand_id": state.hand_id,
                "street": state.street.value,
                "current_bet": state.current_bet,
                "seats": serialized_seats,
                "community_cards": [
                    {"rank": c.rank.value, "suit": c.suit.value} for c in state.community_cards
                ],
                "pots": [
                    {"amount": pot.amount, "eligible_seats": sorted(pot.eligible_seats)}
                    for pot in state.pots
                ],
            },
        }
        
        await websocket.send_json(initial_state_message)
        
        # Broadcast state to all other connections so they see the new connection
        # (This ensures all clients have the latest state when someone new joins)
        other_connections_count = len(manager.active_connections.get(table_id, set())) - 1  # Exclude self
        if other_connections_count > 0:
            print(f"[WS] Broadcasting state to {other_connections_count} other connection(s) on table {table_id}")
            await manager.broadcast(
                table_id,
                state,
                exclude=websocket  # Don't send to the new connection (already sent)
            )
        else:
            print(f"[WS] No other connections to broadcast to on table {table_id}")

        while True:
            # Receive command
            data = await websocket.receive_json()

            command_type = data.get("type")
            if command_type == "sit_down":
                request = SitDownRequest(**data["data"])
                print(f"[WS] Processing sit_down command: player={request.player_id}, seat={request.seat_id}, stack={request.stack}")
                command = SitDown(
                    idempotency_key=data.get("idempotency_key", f"sit-{time.time()}"),
                    timestamp=time.time(),
                    seat_id=request.seat_id,
                    stack=request.stack,
                    player_id=request.player_id,
                )

            elif command_type == "act":
                # Extract action data and required fields
                action_data = data["data"]
                act_idempotency_key = data.get("idempotency_key") or action_data.get("idempotency_key") or f"act-{time.time()}"
                act_expected_version = data.get("expected_version") or action_data.get("expected_version") or 0
                
                # Create request with all required fields
                request = ActRequest(
                    seat_id=action_data["seat_id"],
                    action_type=action_data["action_type"],
                    amount=action_data.get("amount"),
                    idempotency_key=act_idempotency_key,
                    expected_version=act_expected_version,
                )
                command = Act(
                    idempotency_key=act_idempotency_key,
                    timestamp=time.time(),
                    seat_id=request.seat_id,
                    action_type=ActionType(request.action_type),
                    amount=request.amount,
                )
                # Store for use in process_command
                idempotency_key = act_idempotency_key
                expected_version = act_expected_version

            elif command_type == "start_hand":
                request = StartHandRequest(**data["data"])
                print(f"[WS] Processing start_hand command: hand_id={request.hand_id}")
                command = StartHand(
                    idempotency_key=data.get("idempotency_key", f"start-{time.time()}"),
                    timestamp=time.time(),
                    hand_id=request.hand_id,
                    seed_commit=request.seed_commit,
                )

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown command: {command_type}"})
                continue

            # Process command
            try:
                # Use idempotency_key and expected_version from command creation, or fallback to data
                cmd_idempotency_key = idempotency_key if 'idempotency_key' in locals() else data.get("idempotency_key", f"{command_type}-{time.time()}")
                cmd_expected_version = expected_version if 'expected_version' in locals() else data.get("expected_version", 0)
                print(f"[WS] Processing command {command_type}, expected_version={cmd_expected_version}")
                new_state, events, new_version = service.process_command(
                    command, cmd_idempotency_key, cmd_expected_version
                )
                print(f"[WS] Command processed successfully: {len(events)} events, version={new_version}")

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
                
                # Also broadcast updated state after events
                # Force reload to get latest state
                service.current_state = None  # Invalidate cache
                updated_state = service.get_state()
                
                # Get current version for state message
                event_stream_id = service.hand_id or f"table-{service.table_id}"
                current_version = service.event_store.get_current_version(event_stream_id)
                
                # Count seated players for logging
                seated_count = sum(1 for seat in updated_state.seats if seat is not None)
                seated_player_ids = [seat.player_id for seat in updated_state.seats if seat is not None and seat.player_id]
                
                state_message = {
                    "type": "state",
                    "version": current_version,
                    "data": {
                        "hand_id": updated_state.hand_id,
                        "street": updated_state.street.value,
                        "current_bet": updated_state.current_bet,
                        "seats": [
                            seat.model_dump_public() if seat else None for seat in updated_state.seats
                        ],
                        "community_cards": [
                            {"rank": c.rank.value, "suit": c.suit.value} for c in updated_state.community_cards
                        ],
                        "pots": [
                            {"amount": pot.amount, "eligible_seats": sorted(pot.eligible_seats)}
                            for pot in updated_state.pots
                        ],
                    },
                }
                
                # Broadcast to all connections (including sender)
                print(f"[WS] Broadcasting state to table {table_id}: {seated_count} players ({seated_player_ids}), version {current_version}")
                await manager.broadcast(table_id, updated_state)

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

