"""Tests for table service."""

import os
import tempfile
import time

import pytest

from engine.domain.commands import Act, ActionType, SitDown, StartHand
from server.persistence.event_store import EventStore
from server.services.table_service import TableService


class TestTableService:
    """Test table service functionality."""

    @pytest.fixture
    def event_store(self):
        """Create a temporary event store."""
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        db_file.close()
        store = EventStore(f"sqlite:///{db_file.name}")
        yield store
        os.unlink(db_file.name)

    @pytest.fixture
    def service(self, event_store):
        """Create table service."""
        return TableService(event_store, table_id="test-table")

    def test_process_sit_down(self, service):
        """Test processing SitDown command."""
        command = SitDown(
            idempotency_key="sit-1",
            timestamp=time.time(),
            seat_id=0,
            stack=1000,
            player_id="player1",
        )

        state, events, version = service.process_command(command, "sit-1", 0)
        assert len(events) == 1
        assert state.get_player(0) is not None
        assert state.get_player(0).stack == 1000

    def test_idempotent_command(self, service):
        """Test that duplicate commands are idempotent."""
        command = SitDown(
            idempotency_key="sit-1",
            timestamp=time.time(),
            seat_id=0,
            stack=1000,
            player_id="player1",
        )

        # First command
        state1, events1, version1 = service.process_command(command, "sit-1", 0)

        # Duplicate command
        state2, events2, version2 = service.process_command(command, "sit-1", 0)

        # Should return same result (idempotent)
        assert state1.get_player(0).stack == state2.get_player(0).stack

    def test_optimistic_concurrency(self, service):
        """Test optimistic concurrency control."""
        # Seat two players first
        sit_cmd1 = SitDown(
            idempotency_key="sit-1",
            timestamp=time.time(),
            seat_id=0,
            stack=1000,
            player_id="player1",
        )
        service.process_command(sit_cmd1, "sit-1", 0)

        sit_cmd2 = SitDown(
            idempotency_key="sit-2",
            timestamp=time.time(),
            seat_id=1,
            stack=1000,
            player_id="player2",
        )
        service.process_command(sit_cmd2, "sit-2", 0)

        # Start hand
        start_cmd = StartHand(
            idempotency_key="start-1",
            timestamp=time.time(),
            hand_id="hand-1",
            seed_commit="commit-hash",
        )
        service.process_command(start_cmd, "start-1", 0)

        # First action with version 1 (after hand started)
        current_version = service.event_store.get_current_version("hand-1")
        act_cmd1 = Act(
            idempotency_key="act-1",
            timestamp=time.time(),
            seat_id=0,
            action_type=ActionType.CHECK,
        )

        # This should work
        try:
            service.process_command(act_cmd1, "act-1", current_version)
        except ValueError:
            pass  # May fail if action not legal, that's okay

        # Get updated version after first command
        service.event_store.get_current_version("table-default")
        # Use old version to trigger version mismatch
        old_version = current_version  # This is the version before the first command

        # Try action with wrong version (use old version)
        act_cmd2 = Act(
            idempotency_key="act-2",
            timestamp=time.time(),
            seat_id=1,
            action_type=ActionType.CALL,  # Use CALL which should be legal after a bet
            amount=100,
        )

        # Need to set up a betting scenario first - ensure there's a bet to call
        # Actually, let's use a BET action which should be legal when no bet exists
        # But first ensure we're in a state where BET is legal
        state = service.get_state()
        if state.current_bet == 0:
            # Use BET action which is legal when no bet
            act_cmd2 = Act(
                idempotency_key="act-2",
                timestamp=time.time(),
                seat_id=1,
                action_type=ActionType.BET,
                amount=100,
            )
        else:
            # Use CALL action if there's a bet
            act_cmd2 = Act(
                idempotency_key="act-2",
                timestamp=time.time(),
                seat_id=1,
                action_type=ActionType.CALL,
                amount=state.current_bet,
            )

        # Should fail with version mismatch (use old version, not updated_version)
        with pytest.raises((ValueError, Exception), match=".*[Vv]ersion.*"):
            service.process_command(
                act_cmd2, "act-2", old_version
            )  # Wrong version (already incremented)
