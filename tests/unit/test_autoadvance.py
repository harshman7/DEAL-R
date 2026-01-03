"""Tests for auto-advance logic."""

import time

import pytest

from engine.domain.commands import Act, ActionType, SitDown, StartHand
from engine.domain.state import GameState, PlayerStatus, Street
from engine.domain.types import Deck
from engine.reducer.reducer import next_state


class TestAutoAdvance:
    """Test auto-advance functionality."""

    def test_single_player_wins_on_fold(self):
        """Test that single remaining player wins pot automatically."""
        state = GameState(num_seats=6)
        deck = Deck.create_shuffled(42)

        # Seat two players
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

        # Start hand
        state, _ = next_state(
            state,
            StartHand(
                idempotency_key="start-1",
                timestamp=time.time(),
                hand_id="hand-123",
                seed_commit="commit-hash",
            ),
        )

        # Set up for betting (no bet yet, on flop)
        state = state.model_copy(update={"current_bet": 0, "street": Street.FLOP})

        # Player 1 bets
        state, events = next_state(
            state,
            Act(
                idempotency_key="bet-1",
                timestamp=time.time(),
                seat_id=1,
                action_type=ActionType.BET,
                amount=100,
            ),
            deck=deck,
        )

        # Player 0 folds
        state, events = next_state(
            state,
            Act(
                idempotency_key="fold-1",
                timestamp=time.time(),
                seat_id=0,
                action_type=ActionType.FOLD,
            ),
            deck=deck,
        )

        # Should have HandEnded event
        from engine.domain.events import HandEnded

        assert any(isinstance(e, HandEnded) for e in events)
        # Or check state
        assert state.street == Street.COMPLETE

    def test_betting_round_complete_deals_next_street(self):
        """Test that betting round completion deals next street."""
        state = GameState(num_seats=6)
        deck = Deck.create_shuffled(42)

        # Seat two players
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

        # Start hand
        state, _ = next_state(
            state,
            StartHand(
                idempotency_key="start-1",
                timestamp=time.time(),
                hand_id="hand-123",
                seed_commit="commit-hash",
            ),
        )

        # Set up preflop with betting complete
        state = state.model_copy(
            update={
                "street": Street.PREFLOP,
                "current_bet": 100,
            }
        )
        # Both players have acted and are at same commitment
        from engine.domain.state import PlayerState

        player0 = state.get_player(0)
        player1 = state.get_player(1)
        if player0:
            state.seats[0] = player0.model_copy(
                update={"committed_street": 100, "acted_this_street": True}
            )
        if player1:
            state.seats[1] = player1.model_copy(
                update={"committed_street": 100, "acted_this_street": True}
            )

        # Trigger auto-advance by completing betting round
        from engine.reducer.autoadvance import check_auto_advance

        new_state, events = check_auto_advance(state, deck)

        # Should have StreetDealt event for flop
        from engine.domain.events import StreetDealt

        street_events = [e for e in events if isinstance(e, StreetDealt)]
        assert len(street_events) > 0
        assert any(e.street == Street.FLOP for e in street_events)


class TestHandEvaluation:
    """Test hand evaluation."""

    def test_evaluate_royal_flush(self):
        """Test evaluating a royal flush."""
        from engine.domain.types import Card, Rank, Suit
        from engine.eval.evaluator import evaluate_hand, HandRank

        hole = (Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.SPADES))
        board = [
            Card(Rank.QUEEN, Suit.SPADES),
            Card(Rank.JACK, Suit.SPADES),
            Card(Rank.TEN, Suit.SPADES),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.THREE, Suit.CLUBS),
        ]

        hand_value = evaluate_hand(hole, board)
        assert hand_value.rank == HandRank.ROYAL_FLUSH

    def test_evaluate_pair(self):
        """Test evaluating a pair."""
        from engine.domain.types import Card, Rank, Suit
        from engine.eval.evaluator import evaluate_hand, HandRank

        hole = (Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.HEARTS))
        board = [
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.THREE, Suit.CLUBS),
            Card(Rank.FOUR, Suit.DIAMONDS),
            Card(Rank.SIX, Suit.SPADES),
        ]

        hand_value = evaluate_hand(hole, board)
        assert hand_value.rank == HandRank.PAIR
        assert hand_value.kickers[0] == Rank.ACE.value

