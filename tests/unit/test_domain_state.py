"""Tests for domain state: GameState, PlayerState."""

import pytest

from engine.domain.state import GameState, PlayerState, PlayerStatus, Street
from engine.domain.types import Card, Rank, Suit


class TestPlayerState:
    """Test PlayerState model."""

    def test_player_state_creation(self):
        """Test creating a player state."""
        player = PlayerState(
            seat_id=0,
            stack=1000,
            status=PlayerStatus.ACTIVE,
        )
        assert player.seat_id == 0
        assert player.stack == 1000
        assert player.committed_street == 0
        assert player.committed_total == 0
        assert player.status == PlayerStatus.ACTIVE
        assert not player.acted_this_street

    def test_player_state_negative_stack_rejected(self):
        """Test that negative stacks are rejected."""
        with pytest.raises(Exception):  # Pydantic validation error
            PlayerState(seat_id=0, stack=-100)

    def test_player_state_serialization(self):
        """Test player state can be serialized."""
        player = PlayerState(
            seat_id=1,
            stack=5000,
            committed_street=100,
            committed_total=200,
            status=PlayerStatus.ALL_IN,
        )
        data = player.model_dump()
        assert data["seat_id"] == 1
        assert data["stack"] == 5000
        assert data["committed_street"] == 100
        assert data["status"] == "ALL_IN"

    def test_player_state_public_dump_excludes_hole_cards(self):
        """Test that public dump excludes server-only hole_cards."""
        player = PlayerState(
            seat_id=0,
            stack=1000,
            hole_cards=(Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.SPADES)),
        )
        public_data = player.model_dump_public()
        assert "hole_cards" not in public_data


class TestGameState:
    """Test GameState model."""

    def test_game_state_creation(self):
        """Test creating a game state."""
        state = GameState(num_seats=6, small_blind=25, big_blind=50)
        assert state.num_seats == 6
        assert state.small_blind == 25
        assert state.big_blind == 50
        assert len(state.seats) == 6
        assert all(seat is None for seat in state.seats)
        assert state.street == Street.WAITING

    def test_game_state_default_seats(self):
        """Test default 9-seat table."""
        state = GameState()
        assert state.num_seats == 9
        assert len(state.seats) == 9

    def test_game_state_seat_player(self):
        """Test seating a player."""
        state = GameState(num_seats=6)
        player = PlayerState(seat_id=0, stack=1000)
        state.seats[0] = player
        assert state.get_player(0) == player
        assert state.get_player(1) is None

    def test_game_state_get_active_players(self):
        """Test getting active players."""
        state = GameState(num_seats=4)
        state.seats[0] = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE)
        state.seats[1] = PlayerState(seat_id=1, stack=1000, status=PlayerStatus.FOLDED)
        state.seats[2] = PlayerState(seat_id=2, stack=1000, status=PlayerStatus.ALL_IN)
        state.seats[3] = None

        active = state.get_active_players()
        assert len(active) == 2
        assert active[0].seat_id == 0
        assert active[1].seat_id == 2

    def test_game_state_count_active_players(self):
        """Test counting active players."""
        state = GameState(num_seats=3)
        state.seats[0] = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE)
        state.seats[1] = PlayerState(seat_id=1, stack=1000, status=PlayerStatus.FOLDED)
        state.seats[2] = PlayerState(seat_id=2, stack=1000, status=PlayerStatus.ALL_IN)

        assert state.count_active_players() == 2

    def test_game_state_serialization(self):
        """Test game state can be serialized to dict."""
        state = GameState(num_seats=2, small_blind=50, big_blind=100)
        state.seats[0] = PlayerState(seat_id=0, stack=1000)
        state.street = Street.PREFLOP

        data = state.model_dump()
        assert data["num_seats"] == 2
        assert data["street"] == "PREFLOP"
        assert len(data["seats"]) == 2
        assert data["seats"][0] is not None

    def test_game_state_two_player_setup(self):
        """Test setting up a 2-player game state."""
        state = GameState(num_seats=2, small_blind=50, big_blind=100)
        state.seats[0] = PlayerState(seat_id=0, stack=1000, status=PlayerStatus.ACTIVE)
        state.seats[1] = PlayerState(seat_id=1, stack=1000, status=PlayerStatus.ACTIVE)

        # Verify state is valid
        assert state.count_active_players() == 2
        assert state.get_player(0).stack == 1000
        assert state.get_player(1).stack == 1000

        # Serialize and verify
        data = state.model_dump()
        assert len([s for s in data["seats"] if s is not None]) == 2

