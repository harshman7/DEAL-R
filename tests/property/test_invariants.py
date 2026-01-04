"""Property-based tests for game invariants."""

import time
from typing import Optional

import pytest
from hypothesis import given, settings, strategies as st

from engine.domain.commands import Act, ActionType, SitDown, StartHand
from engine.domain.state import GameState, PlayerStatus, Street
from engine.domain.types import Deck
from engine.reducer.reducer import apply_event, next_state
from engine.rules.invariants import (
    check_all_invariants,
    check_chip_conservation,
    check_no_negative_stacks,
    check_pot_correctness,
)


@st.composite
def valid_game_state(draw):
    """Generate a valid game state with 2-6 players."""
    num_seats = draw(st.integers(min_value=2, max_value=6))
    state = GameState(num_seats=num_seats)

    # Seat 2-6 players
    num_players = draw(st.integers(min_value=2, max_value=num_seats))
    for i in range(num_players):
        stack = draw(st.integers(min_value=100, max_value=10000))
        from engine.domain.commands import SitDown

        cmd = SitDown(
            idempotency_key=f"sit-{i}",
            timestamp=time.time(),
            seat_id=i,
            stack=stack,
            player_id=f"player{i}",
        )
        state, _ = next_state(state, cmd)

    return state


@st.composite
def valid_action_sequence(draw, state: GameState):
    """Generate a sequence of valid actions."""
    actions = []
    current_state = state
    max_actions = draw(st.integers(min_value=1, max_value=20))

    for _ in range(max_actions):
        # Find active players
        active_players = [
            (i, player)
            for i, player in enumerate(current_state.seats)
            if player is not None and player.status == PlayerStatus.ACTIVE
        ]

        if not active_players:
            break

        # Pick a random active player
        seat_id, player = draw(st.sampled_from(active_players))

        # Get legal actions
        from engine.rules.legality import compute_legal_actions

        legal_actions = compute_legal_actions(current_state, seat_id)
        if not legal_actions:
            break

        # Pick a random legal action
        action_type = draw(st.sampled_from(list(legal_actions)))

        # Generate amount if needed
        amount: Optional[int] = None
        if action_type in (ActionType.BET, ActionType.RAISE):
            from engine.rules.legality import get_call_amount, get_min_raise_amount

            call_amount = get_call_amount(current_state, seat_id)
            min_raise = get_min_raise_amount(current_state)
            if action_type == ActionType.BET:
                # Bet must be at least big blind
                min_amount = current_state.big_blind
                max_amount = player.stack
            else:
                # Raise must be call_amount + min_raise (or all-in)
                min_amount = call_amount + min_raise
                max_amount = player.stack

            if min_amount <= max_amount:
                amount = draw(st.integers(min_value=min_amount, max_value=max_amount))

        if amount is None or amount <= player.stack:
            action = Act(
                idempotency_key=f"act-{len(actions)}",
                timestamp=time.time(),
                seat_id=seat_id,
                action_type=action_type,
                amount=amount,
            )
            actions.append((current_state, action))
            try:
                current_state, _ = next_state(current_state, action)
            except ValueError:
                # Invalid action, stop generating
                break

    return actions


class TestInvariants:
    """Test that invariants always hold."""

    @given(valid_game_state())
    @settings(max_examples=50, deadline=5000)
    def test_no_negative_stacks(self, state: GameState):
        """Property: No player ever has negative stack."""
        violations = check_all_invariants(state)
        assert check_no_negative_stacks(state), f"Negative stacks found: {violations}"

    @given(valid_game_state())
    @settings(max_examples=50, deadline=5000)
    def test_chip_conservation_initial(self, state: GameState):
        """Property: Chips are conserved in initial state."""
        initial_total = sum(
            (player.stack + player.committed_total)
            for player in state.seats
            if player is not None
        )
        assert check_chip_conservation(initial_total, state)

    @given(valid_game_state())
    @settings(max_examples=10, deadline=20000)
    def test_invariants_after_simple_actions(self, state: GameState):
        """Property: Invariants hold after simple action sequences."""
        initial_total = sum(
            (player.stack + player.committed_total)
            for player in state.seats
            if player is not None
        )

        current_state = state
        deck = Deck.create_shuffled(42)

        # Execute a few simple actions
        for i in range(5):
            # Find active player
            active_players = [
                (j, player)
                for j, player in enumerate(current_state.seats)
                if player is not None and player.status == PlayerStatus.ACTIVE
            ]

            if not active_players:
                break

            seat_id, player = active_players[0]
            from engine.rules.legality import compute_legal_actions

            legal_actions = compute_legal_actions(current_state, seat_id)
            if not legal_actions:
                break

            # Pick a simple action (prefer CHECK/CALL over BET/RAISE for simplicity)
            action_type = ActionType.CHECK if ActionType.CHECK in legal_actions else list(legal_actions)[0]
            amount = None
            if action_type in (ActionType.BET, ActionType.RAISE):
                from engine.rules.legality import get_call_amount, get_min_raise_amount

                call_amount = get_call_amount(current_state, seat_id)
                min_raise = get_min_raise_amount(current_state)
                if action_type == ActionType.BET:
                    amount = current_state.big_blind
                else:
                    amount = call_amount + min_raise
                amount = min(amount, player.stack)

            action = Act(
                idempotency_key=f"act-{i}",
                timestamp=time.time(),
                seat_id=seat_id,
                action_type=action_type,
                amount=amount,
            )

            try:
                current_state, events = next_state(current_state, action, deck=deck)
                # Check invariants after each action
                violations = check_all_invariants(current_state)
                assert (
                    len(violations) == 0
                ), f"Invariant violations after action {action}: {violations}"

                # Check chip conservation
                assert check_chip_conservation(
                    initial_total, current_state
                ), "Chip conservation violated"

            except ValueError:
                # Invalid action, that's okay
                break

        # Check pot correctness if at terminal state
        if current_state.street in (Street.SHOWDOWN, Street.COMPLETE):
            assert check_pot_correctness(
                current_state
            ), "Pot correctness violated at terminal state"


class TestDeterministicReplay:
    """Test deterministic replay invariant."""

    def test_replay_produces_identical_state(self):
        """Test that replaying events produces identical final state."""
        state = GameState(num_seats=6)
        deck = Deck.create_shuffled(42)

        # Seat players
        state, events1 = next_state(
            state,
            SitDown(
                idempotency_key="sit-1",
                timestamp=time.time(),
                seat_id=0,
                stack=1000,
                player_id="player1",
            ),
        )
        state, events2 = next_state(
            state,
            SitDown(
                idempotency_key="sit-2",
                timestamp=time.time(),
                seat_id=1,
                stack=1000,
                player_id="player2",
            ),
        )

        all_events = events1 + events2

        # Replay events from scratch
        replay_state = GameState(num_seats=6)
        for event in all_events:
            replay_state = apply_event(replay_state, event)

        # States should match
        assert state.get_player(0).stack == replay_state.get_player(0).stack
        assert state.get_player(1).stack == replay_state.get_player(1).stack

    @given(valid_game_state())
    @settings(max_examples=20, deadline=10000)
    def test_replay_invariant_property(self, initial_state: GameState):
        """Property: Replaying event log yields identical final state."""
        # Generate action sequence
        actions = []
        current_state = initial_state
        deck = Deck.create_shuffled(42)

        # Collect all events
        all_events = []

        # Execute up to 10 actions
        for i in range(10):
            # Find active player
            active_players = [
                (j, player)
                for j, player in enumerate(current_state.seats)
                if player is not None and player.status == PlayerStatus.ACTIVE
            ]

            if not active_players:
                break

            # Pick first active player and first legal action
            seat_id, player = active_players[0]
            from engine.rules.legality import compute_legal_actions

            legal_actions = compute_legal_actions(current_state, seat_id)
            if not legal_actions:
                break

            action_type = list(legal_actions)[0]
            amount = None
            if action_type in (ActionType.BET, ActionType.RAISE):
                from engine.rules.legality import get_call_amount, get_min_raise_amount

                call_amount = get_call_amount(current_state, seat_id)
                min_raise = get_min_raise_amount(current_state)
                if action_type == ActionType.BET:
                    amount = current_state.big_blind
                else:
                    amount = call_amount + min_raise
                amount = min(amount, player.stack)

            action = Act(
                idempotency_key=f"act-{i}",
                timestamp=time.time(),
                seat_id=seat_id,
                action_type=action_type,
                amount=amount,
            )

            try:
                new_state, events = next_state(current_state, action, deck=deck)
                all_events.extend(events)
                current_state = new_state
            except ValueError:
                break

        # Replay all events from initial state
        replay_state = initial_state
        for event in all_events:
            replay_state = apply_event(replay_state, event)

        # Final states should be identical (at least for key properties)
        assert (
            current_state.count_active_players() == replay_state.count_active_players()
        )
        for i in range(len(current_state.seats)):
            player1 = current_state.get_player(i)
            player2 = replay_state.get_player(i)
            if player1 is None and player2 is None:
                continue
            if player1 is None or player2 is None:
                assert False, f"Player mismatch at seat {i}"
            assert player1.stack == player2.stack, f"Stack mismatch at seat {i}"
            assert (
                player1.committed_total == player2.committed_total
            ), f"Committed total mismatch at seat {i}"

