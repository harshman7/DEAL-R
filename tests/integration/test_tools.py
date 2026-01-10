"""Integration tests for CLI tools."""

import tempfile
import time
from pathlib import Path

import pytest

from engine.domain.commands import SitDown, StartHand
from server.persistence.event_store import EventStore
from server.services.table_service import TableService
from tools.hh_export import export_hand_history
from tools.replay_cli import hash_state, replay_hand


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    db_path = db_file.name
    db_file.close()
    db_url = f"sqlite:///{db_path}"
    yield db_url
    Path(db_path).unlink(missing_ok=True)


def test_replay_cli_hash_state(temp_db):
    """Test state hashing function."""
    from engine.domain.state import GameState

    state1 = GameState(num_seats=9)
    state2 = GameState(num_seats=9)

    # Same state should produce same hash
    assert hash_state(state1) == hash_state(state2)

    # Different state should produce different hash
    state2.small_blind = 10
    assert hash_state(state1) != hash_state(state2)


def test_replay_cli_replay_hand(temp_db):
    """Test replaying a hand from events."""
    # Setup: Create a hand with events

    event_store = EventStore(temp_db)
    table_service = TableService(event_store, table_id="test-table")
    hand_id = "test-hand-1"

    # Sit down players
    table_service.process_command(
        command=SitDown(
            idempotency_key="sit1",
            timestamp=time.time(),
            seat_id=0,
            player_id="player1",
            stack=1000,
        ),
        idempotency_key="sit1",
        expected_version=0,
    )
    table_service.process_command(
        command=SitDown(
            idempotency_key="sit2",
            timestamp=time.time(),
            seat_id=1,
            player_id="player2",
            stack=1000,
        ),
        idempotency_key="sit2",
        expected_version=0,
    )

    # Start hand
    table_service.process_command(
        command=StartHand(
            idempotency_key="start1",
            timestamp=time.time(),
            hand_id=hand_id,
            seed_commit="abc123",
        ),
        idempotency_key="start1",
        expected_version=0,
    )

    # Replay hand
    state, state_hash = replay_hand(hand_id, temp_db)

    # Verify state
    assert state.street.value == "PREFLOP"
    assert state_hash is not None
    assert len(state_hash) == 64  # SHA256 hex length

    # Verify hash is deterministic
    state2, state_hash2 = replay_hand(hand_id, temp_db)
    assert state_hash == state_hash2


def test_hh_export(temp_db, tmp_path):
    """Test hand history export."""
    # Setup: Create a hand with events

    event_store = EventStore(temp_db)
    table_service = TableService(event_store, table_id="test-table")
    hand_id = "test-hand-2"

    # Sit down players
    table_service.process_command(
        command=SitDown(
            idempotency_key="sit3",
            timestamp=time.time(),
            seat_id=0,
            player_id="player1",
            stack=1000,
        ),
        idempotency_key="sit3",
        expected_version=0,
    )
    table_service.process_command(
        command=SitDown(
            idempotency_key="sit4",
            timestamp=time.time(),
            seat_id=1,
            player_id="player2",
            stack=1000,
        ),
        idempotency_key="sit4",
        expected_version=0,
    )

    # Start hand
    table_service.process_command(
        command=StartHand(
            idempotency_key="start2",
            timestamp=time.time(),
            hand_id=hand_id,
            seed_commit="xyz789",
        ),
        idempotency_key="start2",
        expected_version=0,
    )

    # Export to file
    output_file = tmp_path / "hand_history.txt"
    export_hand_history(hand_id, temp_db, str(output_file))

    # Verify file was created and contains expected content
    assert output_file.exists()
    content = output_file.read_text()
    assert "Hand #" in content
    assert hand_id in content
    assert "HAND STARTED" in content or "Hand Started" in content
    assert "Button:" in content or "button" in content.lower()


def test_replay_cli_nonexistent_hand(temp_db):
    """Test replay CLI with non-existent hand."""
    # Should return empty state (no events)
    state, state_hash = replay_hand("nonexistent-hand", temp_db)
    assert state.street.value == "WAITING"
    assert state_hash is not None


def test_hh_export_nonexistent_hand(temp_db):
    """Test hand history export with non-existent hand."""
    import sys
    from io import StringIO

    # Capture stderr
    old_stderr = sys.stderr
    sys.stderr = StringIO()

    try:
        export_hand_history("nonexistent-hand", temp_db, None)
        # Should have written error to stderr
        stderr_content = sys.stderr.getvalue()
        assert "No events found" in stderr_content or len(stderr_content) > 0
    except SystemExit:
        pass  # Expected
    finally:
        sys.stderr = old_stderr
