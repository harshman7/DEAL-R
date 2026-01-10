"""Tests for betting legality and round completion."""

import time

from engine.domain.commands import ActionType, SitDown, StartHand
from engine.domain.state import GameState, PlayerState, PlayerStatus, Street
from engine.reducer.reducer import next_state
from engine.rules.legality import (
    calculate_action_amount,
    compute_legal_actions,
    get_call_amount,
    get_min_raise_amount,
    is_betting_round_complete,
    validate_action,
)


class TestLegalActions:
    """Test legal actions computation."""

    def test_check_when_no_bet(self):
        """Test CHECK is legal when no bet exists."""
        state = GameState(num_seats=6, small_blind=50, big_blind=100)
        state.seats[0] = (
            type(state.seats[0])(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE)
            if state.seats[0]
            else None
        )

        # Actually use reducer to set up properly
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

        # After blinds, there should be a bet
        # But for testing, let's check on a street with no bet
        state = state.model_copy(update={"current_bet": 0, "street": Street.FLOP})

        legal = compute_legal_actions(state, 0)
        assert ActionType.CHECK in legal
        assert ActionType.BET in legal
        assert ActionType.FOLD not in legal  # No bet to fold to
        assert ActionType.CALL not in legal  # No bet to call

    def test_call_when_bet_exists(self):
        """Test CALL is legal when bet exists."""
        state = GameState(num_seats=6)
        player = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE, committed_street=0)
        state.seats[0] = player
        state = state.model_copy(update={"current_bet": 100, "street": Street.PREFLOP})

        legal = compute_legal_actions(state, 0)
        assert ActionType.CALL in legal
        assert ActionType.FOLD in legal
        assert ActionType.CHECK not in legal
        assert ActionType.BET not in legal  # Can't bet when bet exists
        assert ActionType.RAISE in legal

    def test_bet_when_no_bet(self):
        """Test BET is legal when no bet exists."""
        state = GameState(num_seats=6)
        player = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE)
        state.seats[0] = player
        state = state.model_copy(update={"current_bet": 0, "street": Street.FLOP})

        legal = compute_legal_actions(state, 0)
        assert ActionType.BET in legal
        assert ActionType.CHECK in legal
        assert ActionType.RAISE not in legal  # Can't raise when no bet

    def test_fold_requires_bet(self):
        """Test FOLD is only legal when there's a bet."""
        state = GameState(num_seats=6)
        player = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE)
        state.seats[0] = player

        # No bet
        state = state.model_copy(update={"current_bet": 0, "street": Street.FLOP})
        legal = compute_legal_actions(state, 0)
        assert ActionType.FOLD not in legal

        # With bet
        state = state.model_copy(update={"current_bet": 100})
        legal = compute_legal_actions(state, 0)
        assert ActionType.FOLD in legal


class TestCallAmount:
    """Test call amount calculation."""

    def test_call_amount_no_bet(self):
        """Test call amount is 0 when no bet."""
        state = GameState(num_seats=6)
        state.seats[0] = (
            type(state.seats[0])(
                seat_id=0, stack=1000, status=PlayerStatus.ACTIVE, committed_street=0
            )
            if state.seats[0]
            else None
        )
        state = state.model_copy(update={"current_bet": 0})

        assert get_call_amount(state, 0) == 0

    def test_call_amount_with_bet(self):
        """Test call amount calculation."""
        state = GameState(num_seats=6)
        player = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE, committed_street=50)
        state.seats[0] = player
        state = state.model_copy(update={"current_bet": 100})

        assert get_call_amount(state, 0) == 50  # 100 - 50 = 50

    def test_call_amount_already_at_bet(self):
        """Test call amount is 0 when already at bet."""
        state = GameState(num_seats=6)
        state.seats[0] = (
            type(state.seats[0])(
                seat_id=0, stack=1000, status=PlayerStatus.ACTIVE, committed_street=100
            )
            if state.seats[0]
            else None
        )
        state = state.model_copy(update={"current_bet": 100})

        assert get_call_amount(state, 0) == 0


class TestMinRaise:
    """Test minimum raise calculation."""

    def test_min_raise_no_bet(self):
        """Test min raise is big blind when no bet."""
        state = GameState(num_seats=6, big_blind=100)
        state = state.model_copy(update={"current_bet": 0, "min_raise": 0})

        assert get_min_raise_amount(state) == 100

    def test_min_raise_first_bet(self):
        """Test min raise after first bet."""
        state = GameState(num_seats=6, big_blind=100)
        state = state.model_copy(update={"current_bet": 200, "min_raise": 200})

        # Min raise is the last raise increment
        assert get_min_raise_amount(state) == 200


class TestActionValidation:
    """Test action validation."""

    def test_validate_check_no_bet(self):
        """Test CHECK validation when no bet."""
        state = GameState(num_seats=6)
        player = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE)
        state.seats[0] = player
        state = state.model_copy(update={"current_bet": 0, "street": Street.FLOP})

        is_valid, msg = validate_action(state, 0, ActionType.CHECK)
        assert is_valid, msg

    def test_validate_check_with_bet(self):
        """Test CHECK validation fails when bet exists."""
        state = GameState(num_seats=6)
        player = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE)
        state.seats[0] = player
        state = state.model_copy(update={"current_bet": 100, "street": Street.FLOP})

        is_valid, msg = validate_action(state, 0, ActionType.CHECK)
        assert not is_valid
        assert "check" in msg.lower()

    def test_validate_bet_minimum(self):
        """Test BET must be at least big blind."""
        state = GameState(num_seats=6, big_blind=100)
        player = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE)
        state.seats[0] = player
        state = state.model_copy(update={"current_bet": 0, "street": Street.FLOP})

        # Too small
        is_valid, msg = validate_action(state, 0, ActionType.BET, amount=50)
        assert not is_valid

        # Valid
        is_valid, msg = validate_action(state, 0, ActionType.BET, amount=100)
        assert is_valid, msg

    def test_validate_raise_minimum(self):
        """Test RAISE must meet minimum raise."""
        state = GameState(num_seats=6, big_blind=100)
        player = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE, committed_street=0)
        state.seats[0] = player
        state = state.model_copy(
            update={"current_bet": 100, "min_raise": 100, "street": Street.PREFLOP}
        )

        # Raise too small (only 50 more)
        is_valid, msg = validate_action(state, 0, ActionType.RAISE, amount=150)
        assert not is_valid

        # Valid raise (100 more = min raise)
        is_valid, msg = validate_action(state, 0, ActionType.RAISE, amount=200)
        assert is_valid, msg


class TestBettingRoundCompletion:
    """Test betting round completion detection."""

    def test_round_complete_all_checked(self):
        """Test round complete when all players checked."""
        state = GameState(num_seats=6)
        state.seats[0] = (
            type(state.seats[0])(
                seat_id=0,
                stack=1000,
                status=PlayerStatus.ACTIVE,
                committed_street=0,
                acted_this_street=True,
            )
            if state.seats[0]
            else None
        )
        state.seats[1] = (
            type(state.seats[1])(
                seat_id=1,
                stack=1000,
                status=PlayerStatus.ACTIVE,
                committed_street=0,
                acted_this_street=True,
            )
            if state.seats[1]
            else None
        )
        state = state.model_copy(update={"current_bet": 0, "street": Street.FLOP})

        assert is_betting_round_complete(state)

    def test_round_not_complete_player_not_acted(self):
        """Test round not complete when player hasn't acted."""
        state = GameState(num_seats=6)
        player0 = PlayerState(
            seat_id=0,
            stack=1000,
            status=PlayerStatus.ACTIVE,
            committed_street=0,
            acted_this_street=False,
        )
        player1 = PlayerState(
            seat_id=1,
            stack=1000,
            status=PlayerStatus.ACTIVE,
            committed_street=0,
            acted_this_street=True,
        )
        state.seats[0] = player0
        state.seats[1] = player1
        state = state.model_copy(update={"current_bet": 0, "street": Street.FLOP})

        assert not is_betting_round_complete(state)


class TestActionAmountCalculation:
    """Test action amount calculation."""

    def test_calculate_call_amount(self):
        """Test calculating call amount."""
        state = GameState(num_seats=6)
        player = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE, committed_street=50)
        state.seats[0] = player
        state = state.model_copy(update={"current_bet": 100})

        amount = calculate_action_amount(state, 0, ActionType.CALL)
        assert amount == 50

    def test_calculate_call_all_in(self):
        """Test call goes all-in if insufficient chips."""
        state = GameState(num_seats=6)
        player = PlayerState(seat_id=0, stack=30, status=PlayerStatus.ACTIVE, committed_street=50)
        state.seats[0] = player
        state = state.model_copy(update={"current_bet": 100})

        amount = calculate_action_amount(state, 0, ActionType.CALL)
        assert amount == 30  # All-in

    def test_calculate_bet_amount(self):
        """Test calculating bet amount."""
        state = GameState(num_seats=6, big_blind=100)
        player = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE)
        state.seats[0] = player
        state = state.model_copy(update={"current_bet": 0})

        amount = calculate_action_amount(state, 0, ActionType.BET, requested_amount=200)
        assert amount == 200
