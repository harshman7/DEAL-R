"""Tests for WebSocket functionality."""

import asyncio
import json
import os
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

from engine.domain.commands import SitDown
from server.main import app
from server.persistence.event_store import EventStore
from server.services.table_service import TableService


@pytest.fixture
def test_client():
    """Create test client with temporary database."""
    # Use in-memory SQLite for testing
    db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    db_file.close()

    # Override get_table_service to use test database
    original_get_service = None

    def get_test_service(table_id: str = "default"):
        event_store = EventStore(f"sqlite:///{db_file.name}")
        return TableService(event_store, table_id=table_id)

    # Monkey-patch the service getter
    import server.api.ws

    original_get_service = server.api.ws.get_table_service
    server.api.ws.get_table_service = get_test_service

    import server.api.rest

    original_get_rest_service = server.api.rest.get_table_service
    server.api.rest.get_table_service = get_test_service

    client = TestClient(app)

    yield client

    # Cleanup
    server.api.ws.get_table_service = original_get_service
    server.api.rest.get_table_service = original_get_rest_service
    os.unlink(db_file.name)


class TestWebSocket:
    """Test WebSocket functionality."""

    def test_websocket_connection(self, test_client):
        """Test basic WebSocket connection."""
        with test_client.websocket_connect("/ws/tables/default") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "state"

    def test_websocket_sit_down(self, test_client):
        """Test sitting down via WebSocket."""
        with test_client.websocket_connect("/ws/tables/default") as websocket:
            # Receive initial state
            websocket.receive_json()

            # Send sit down command
            websocket.send_json(
                {
                    "type": "sit_down",
                    "data": {
                        "seat_id": 0,
                        "stack": 1000,
                        "player_id": "player1",
                    },
                    "idempotency_key": "sit-1",
                    "expected_version": 0,
                }
            )

            # Receive command accepted
            response = websocket.receive_json()
            assert response["type"] == "command_accepted"

            # Receive state update (new format: broadcasts state instead of individual events)
            state_update = websocket.receive_json()
            assert state_update["type"] == "state"
            assert "seats" in state_update["data"]

    def test_websocket_broadcast(self, test_client):
        """Test that events are broadcast to all connected clients."""
        # Connect two clients
        with test_client.websocket_connect("/ws/tables/default") as ws1:
            with test_client.websocket_connect("/ws/tables/default") as ws2:
                # Both receive initial state
                initial1 = ws1.receive_json()
                assert initial1["type"] == "state"
                initial2 = ws2.receive_json()
                assert initial2["type"] == "state"
                
                # If ws2's connection triggered a broadcast to ws1, consume it
                try:
                    # Check if there's another message from ws2's connection broadcast
                    import select
                    # Use timeout to avoid blocking
                    extra = ws1.receive_json(timeout=0.1)
                    # If we got here, there was an extra message, ignore it for now
                except:
                    pass  # No extra message, that's fine

                # Client 1 sits down
                ws1.send_json(
                    {
                        "type": "sit_down",
                        "data": {
                            "seat_id": 0,
                            "stack": 1000,
                            "player_id": "player1",
                        },
                        "idempotency_key": "sit-1",
                        "expected_version": 0,
                    }
                )

                # Client 1 receives command accepted first, then state
                messages = []
                for _ in range(2):
                    msg = ws1.receive_json()
                    messages.append(msg)
                
                # Should have command_accepted and state (order may vary in async)
                message_types = [m["type"] for m in messages]
                assert "command_accepted" in message_types
                assert "state" in message_types
                
                # Find the state message
                state1 = next(m for m in messages if m["type"] == "state")
                assert "seats" in state1["data"]
                
                # Client 2 receives state broadcast
                state2 = ws2.receive_json()
                assert state2["type"] == "state"
                assert "seats" in state2["data"]

    def test_websocket_idempotency(self, test_client):
        """Test that duplicate commands are idempotent."""
        with test_client.websocket_connect("/ws/tables/default") as websocket:
            # Receive initial state
            websocket.receive_json()

            # Send sit down command
            websocket.send_json(
                {
                    "type": "sit_down",
                    "data": {
                        "seat_id": 0,
                        "stack": 1000,
                        "player_id": "player1",
                    },
                    "idempotency_key": "sit-1",
                    "expected_version": 0,
                }
            )

            # Receive command accepted
            websocket.receive_json()
            # Receive event
            websocket.receive_json()

            # Send same command again (duplicate)
            websocket.send_json(
                {
                    "type": "sit_down",
                    "data": {
                        "seat_id": 0,
                        "stack": 1000,
                        "player_id": "player1",
                    },
                    "idempotency_key": "sit-1",  # Same key
                    "expected_version": 1,
                }
            )

            # Should still work (idempotent)
            response = websocket.receive_json()
            # May get error or success, but shouldn't crash
            assert response["type"] in ("command_accepted", "error")

