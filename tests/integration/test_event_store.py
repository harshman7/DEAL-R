"""Tests for event store."""

import os
import tempfile

import pytest

from engine.domain.commands import SitDown
from engine.domain.events import PlayerSatDown
from server.persistence.event_store import EventStore


class TestEventStore:
    """Test event store functionality."""

    @pytest.fixture
    def event_store(self):
        """Create a temporary event store."""
        # Use in-memory SQLite for testing
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        db_file.close()
        store = EventStore(f"sqlite:///{db_file.name}")
        yield store
        os.unlink(db_file.name)

    def test_append_events(self, event_store):
        """Test appending events."""
        hand_id = "test-hand-1"
        event = PlayerSatDown(
            timestamp=1000.0, seat_id=0, player_id="player1", stack=1000
        )

        version = event_store.append_events(hand_id, 0, [event])
        assert version == 1

    def test_append_events_version_mismatch(self, event_store):
        """Test that version mismatch raises error."""
        hand_id = "test-hand-1"
        event = PlayerSatDown(
            timestamp=1000.0, seat_id=0, player_id="player1", stack=1000
        )

        # Append first event
        event_store.append_events(hand_id, 0, [event])

        # Try to append with wrong expected version
        with pytest.raises(ValueError, match="Version mismatch"):
            event_store.append_events(hand_id, 0, [event])

    def test_get_events(self, event_store):
        """Test retrieving events."""
        hand_id = "test-hand-1"
        event1 = PlayerSatDown(
            timestamp=1000.0, seat_id=0, player_id="player1", stack=1000
        )
        event2 = PlayerSatDown(
            timestamp=1001.0, seat_id=1, player_id="player2", stack=2000
        )

        event_store.append_events(hand_id, 0, [event1])
        event_store.append_events(hand_id, 1, [event2])

        events = event_store.get_events(hand_id)
        assert len(events) == 2

    def test_get_current_version(self, event_store):
        """Test getting current version."""
        hand_id = "test-hand-1"
        assert event_store.get_current_version(hand_id) == 0

        event = PlayerSatDown(
            timestamp=1000.0, seat_id=0, player_id="player1", stack=1000
        )
        event_store.append_events(hand_id, 0, [event])
        assert event_store.get_current_version(hand_id) == 1

    def test_idempotency(self, event_store):
        """Test command idempotency."""
        idempotency_key = "cmd-123"
        hand_id = "test-hand-1"

        # First command
        result1 = event_store.record_command(
            idempotency_key, hand_id, "SitDown", '{"seat_id": 0}'
        )
        assert result1 is True

        # Duplicate command
        result2 = event_store.record_command(
            idempotency_key, hand_id, "SitDown", '{"seat_id": 0}'
        )
        assert result2 is False  # Duplicate

