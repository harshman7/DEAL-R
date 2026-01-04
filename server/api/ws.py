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

    async def connect(self, websocket: WebSocket, table_id: str):
        """Accept a WebSocket connection."""
        await websocket.accept()
        if table_id not in self.active_connections:
            self.active_connections[table_id] = set()
        self.active_connections[table_id].add(websocket)

    def disconnect(self, websocket: WebSocket, table_id: str):
        """Remove a WebSocket connection."""
        if table_id in self.active_connections:
            self.active_connections[table_id].discard(websocket)

    async def broadcast(self, table_id: str, message: dict):
        """Broadcast message to all connections on a table."""
        if table_id not in self.active_connections:
            return

        disconnected = set()
        for connection in self.active_connections[table_id]:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)

        # Remove disconnected connections
        for conn in disconnected:
            self.active_connections[table_id].discard(conn)


# Global connection manager
manager = ConnectionManager()


def get_table_service(table_id: str = "default") -> TableService:
    """Get table service instance."""
    from server.persistence.event_store import EventStore

    event_store = EventStore("sqlite:///./poker.db")
    service = TableService(event_store, table_id=table_id)
    return service


@router.websocket("/ws/tables/{table_id}")
async def websocket_endpoint(websocket: WebSocket, table_id: str):
    """WebSocket endpoint for table updates."""
    await manager.connect(websocket, table_id)
    service = get_table_service(table_id)

    try:
        # Send initial state
        state = service.get_state()
        await websocket.send_json(
            {
                "type": "state",
                "data": {
                    "hand_id": state.hand_id,
                    "street": state.street.value,
                    "seats": [
                        seat.model_dump_public() if seat else None for seat in state.seats
                    ],
                },
            }
        )

        while True:
            # Receive command
            data = await websocket.receive_json()

            command_type = data.get("type")
            if command_type == "sit_down":
                request = SitDownRequest(**data["data"])
                command = SitDown(
                    idempotency_key=data.get("idempotency_key", f"sit-{time.time()}"),
                    timestamp=time.time(),
                    seat_id=request.seat_id,
                    stack=request.stack,
                    player_id=request.player_id,
                )

            elif command_type == "act":
                request = ActRequest(**data["data"])
                command = Act(
                    idempotency_key=request.idempotency_key,
                    timestamp=time.time(),
                    seat_id=request.seat_id,
                    action_type=ActionType(request.action_type),
                    amount=request.amount,
                )

            elif command_type == "start_hand":
                request = StartHandRequest(**data["data"])
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
                expected_version = data.get("expected_version", 0)
                new_state, events, new_version = service.process_command(
                    command, data.get("idempotency_key", ""), expected_version
                )

                # Send success response
                await websocket.send_json(
                    {
                        "type": "command_accepted",
                        "idempotency_key": data.get("idempotency_key"),
                        "new_version": new_version,
                    }
                )

                # Broadcast events to all connections
                for event in events:
                    await manager.broadcast(
                        table_id,
                        {
                            "type": "event",
                            "event_type": type(event).__name__,
                            "event_data": event.__dict__,
                            "version": new_version - len(events) + events.index(event) + 1,
                            "timestamp": event.timestamp,
                        },
                    )

            except ValueError as e:
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        manager.disconnect(websocket, table_id)

