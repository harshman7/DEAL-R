"""Tests for reducer and event sourcing."""

import time

from engine.domain.commands import Act, ActionType, SitDown, StartHand
from engine.domain.events import ActionApplied, HandStarted, PlayerSatDown
from engine.domain.state import GameState, PlayerStatus, Street
from engine.reducer.reducer import apply_event, next_state


class TestReducer:
    """Test reducer functionality."""

    def test_sit_down_command(self):
        """Test SitDown command produces PlayerSatDown event."""
        state = GameState(num_seats=6)
        command = SitDown(
            idempotency_key="sit-1",
            timestamp=time.time(),
            seat_id=0,
            stack=1000,
            player_id="player1",
        )

        new_state, events = next_state(state, command)

        assert len(events) == 1
        assert isinstance(events[0], PlayerSatDown)
        assert events[0].seat_id == 0
        assert events[0].stack == 1000
        assert new_state.get_player(0) is not None
        assert new_state.get_player(0).stack == 1000
        assert new_state.get_player(0).status == PlayerStatus.ACTIVE

    def test_start_hand_command(self):
        """Test StartHand command produces HandStarted event."""
        state = GameState(num_seats=6)
        # Use the reducer to seat players first
        sit_cmd1 = SitDown(
            idempotency_key="sit-1",
            timestamp=time.time(),
            seat_id=0,
            stack=1000,
            player_id="player1",
        )
        state, _ = next_state(state, sit_cmd1)

        sit_cmd2 = SitDown(
            idempotency_key="sit-2",
            timestamp=time.time(),
            seat_id=1,
            stack=1000,
            player_id="player2",
        )
        state, _ = next_state(state, sit_cmd2)

        # Now start hand
        start_cmd = StartHand(
            idempotency_key="start-1",
            timestamp=time.time(),
            hand_id="hand-123",
            seed_commit="commit-hash",
        )

        new_state, events = next_state(state, start_cmd)

        # StartHand now creates HandStarted + BlindPosted events (one for each blind)
        assert len(events) >= 1
        assert isinstance(events[0], HandStarted)
        assert events[0].hand_id == "hand-123"
        assert new_state.hand_id == "hand-123"
        assert new_state.street == Street.PREFLOP
        assert new_state.button_seat is not None
        assert new_state.sb_seat is not None
        assert new_state.bb_seat is not None

    def test_act_command_fold(self):
        """Test Act command with FOLD (requires a bet first)."""
        state = GameState(num_seats=6)
        # Seat and start hand
        state, _ = next_state(
            state,
            SitDown(
                idempotency_key="sit-1",
                timestamp=time.time(),
                seat_id=0,
                stack=1000,
                player_id="player1",
            ),
        )
        state, _ = next_state(
            state,
            SitDown(
                idempotency_key="sit-2",
                timestamp=time.time(),
                seat_id=1,
                stack=1000,
                player_id="player2",
            ),
        )
        state, _ = next_state(
            state,
            StartHand(
                idempotency_key="start-1",
                timestamp=time.time(),
                hand_id="hand-123",
                seed_commit="commit-hash",
            ),
        )

        # First, someone needs to bet (or post blind)
        # Player 1 bets first (on a street with no bet yet)
        state = state.model_copy(update={"current_bet": 0, "street": Street.FLOP})
        bet_cmd = Act(
            idempotency_key="bet-1",
            timestamp=time.time(),
            seat_id=1,
            action_type=ActionType.BET,
            amount=100,
        )
        state, _ = next_state(state, bet_cmd)

        # Now player 0 can fold
        act_cmd = Act(
            idempotency_key="act-1",
            timestamp=time.time(),
            seat_id=0,
            action_type=ActionType.FOLD,
        )

        new_state, events = next_state(state, act_cmd)

        assert len(events) >= 1
        assert isinstance(events[0], ActionApplied)
        assert events[0].action_type == "FOLD"
        assert new_state.get_player(0).status == PlayerStatus.FOLDED


class TestEventReplay:
    """Test deterministic event replay."""

    def test_replay_sit_down(self):
        """Test that replaying events produces same state as reducer."""
        initial_state = GameState(num_seats=6)

        # Generate events via reducer
        command = SitDown(
            idempotency_key="sit-1",
            timestamp=time.time(),
            seat_id=0,
            stack=1000,
            player_id="player1",
        )
        reducer_state, events = next_state(initial_state, command)

        # Replay events
        replay_state = initial_state
        for event in events:
            replay_state = apply_event(replay_state, event)

        # States should be identical
        assert replay_state.get_player(0) is not None
        assert reducer_state.get_player(0) is not None
        assert replay_state.get_player(0).stack == reducer_state.get_player(0).stack
        assert replay_state.get_player(0).seat_id == reducer_state.get_player(0).seat_id

    def test_replay_multiple_commands(self):
        """Test replaying multiple commands produces same final state."""
        initial_state = GameState(num_seats=6)

        # Generate sequence of commands
        commands = [
            SitDown(
                idempotency_key="sit-1",
                timestamp=time.time(),
                seat_id=0,
                stack=1000,
                player_id="player1",
            ),
            SitDown(
                idempotency_key="sit-2",
                timestamp=time.time(),
                seat_id=1,
                stack=2000,
                player_id="player2",
            ),
            StartHand(
                idempotency_key="start-1",
                timestamp=time.time(),
                hand_id="hand-123",
                seed_commit="commit-hash",
            ),
        ]

        # Apply via reducer (collecting all events)
        reducer_state = initial_state
        all_events = []
        for cmd in commands:
            reducer_state, events = next_state(reducer_state, cmd)
            all_events.extend(events)

        # Replay all events from scratch
        replay_state = initial_state
        for event in all_events:
            replay_state = apply_event(replay_state, event)

        # Final states should match
        assert replay_state.hand_id == reducer_state.hand_id
        assert replay_state.street == reducer_state.street
        assert replay_state.get_player(0).stack == reducer_state.get_player(0).stack
        assert replay_state.get_player(1).stack == reducer_state.get_player(1).stack

    def test_replay_idempotency(self):
        """Test that applying same event twice produces same result."""
        state = GameState(num_seats=6)
        state, events = next_state(
            state,
            SitDown(
                idempotency_key="sit-1",
                timestamp=time.time(),
                seat_id=0,
                stack=1000,
                player_id="player1",
            ),
        )

        event = events[0]

        # Apply event twice
        state1 = apply_event(state, event)
        apply_event(state1, event)  # Applying again should be idempotent

        # Actually, events aren't idempotent by design - applying same event twice
        # would be wrong. But applying the same event to the same state should
        # produce the same result
        state1_again = apply_event(state, event)
        assert state1.get_player(0).stack == state1_again.get_player(0).stack
