"""Tests for side pot calculation."""

from engine.domain.state import GameState, PlayerState, PlayerStatus
from engine.rules.sidepots import build_side_pots, get_pot_distribution, validate_pot_invariant


class TestSidePots:
    """Test side pot building."""

    def test_simple_pot_no_all_ins(self):
        """Test simple pot with no all-ins."""
        state = GameState(num_seats=6)
        player0 = PlayerState(seat_id=0, stack=0, committed_total=100, status=PlayerStatus.ACTIVE)
        player1 = PlayerState(seat_id=1, stack=0, committed_total=100, status=PlayerStatus.ACTIVE)
        state.seats[0] = player0
        state.seats[1] = player1

        pots = build_side_pots(state)

        assert len(pots) == 1
        assert pots[0].amount == 200  # 100 * 2 players
        assert pots[0].eligible_seats == {0, 1}
        assert validate_pot_invariant(state, pots)

    def test_side_pot_one_all_in(self):
        """Test side pot with one all-in."""
        state = GameState(num_seats=6)
        player0 = PlayerState(seat_id=0, stack=0, committed_total=1000, status=PlayerStatus.ALL_IN)
        player1 = PlayerState(seat_id=1, stack=500, committed_total=500, status=PlayerStatus.ACTIVE)
        state.seats[0] = player0
        state.seats[1] = player1

        pots = build_side_pots(state)

        assert len(pots) == 2
        # Main pot: both players contribute 500 each = 1000
        assert pots[0].amount == 1000
        assert pots[0].eligible_seats == {0, 1}
        # Side pot: only player0 contributes 500 more = 500
        assert pots[1].amount == 500
        assert pots[1].eligible_seats == {0}
        assert validate_pot_invariant(state, pots)

    def test_three_player_two_all_ins(self):
        """Test 3-player scenario with two all-ins at different amounts."""
        state = GameState(num_seats=6)
        # Player 0: all-in for 1000
        player0 = PlayerState(seat_id=0, stack=0, committed_total=1000, status=PlayerStatus.ALL_IN)
        # Player 1: all-in for 500
        player1 = PlayerState(seat_id=1, stack=0, committed_total=500, status=PlayerStatus.ALL_IN)
        # Player 2: committed 500, still has chips
        player2 = PlayerState(seat_id=2, stack=500, committed_total=500, status=PlayerStatus.ACTIVE)

        state.seats[0] = player0
        state.seats[1] = player1
        state.seats[2] = player2

        pots = build_side_pots(state)

        # Should create:
        # Main pot: 500 * 3 = 1500 (all eligible)
        # Side pot: 500 * 1 = 500 (only player0 eligible)
        assert len(pots) == 2

        # Main pot: all three contribute 500 each
        assert pots[0].amount == 1500
        assert pots[0].eligible_seats == {0, 1, 2}

        # Side pot: only player0 contributes 500 more
        assert pots[1].amount == 500
        assert pots[1].eligible_seats == {0}

        # Validate invariant
        assert validate_pot_invariant(state, pots)
        total_committed = 1000 + 500 + 500
        total_pots = 1500 + 500
        assert total_committed == total_pots

    def test_three_all_ins_different_amounts(self):
        """Test three all-ins at different amounts."""
        state = GameState(num_seats=6)
        player0 = PlayerState(seat_id=0, stack=0, committed_total=1000, status=PlayerStatus.ALL_IN)
        player1 = PlayerState(seat_id=1, stack=0, committed_total=500, status=PlayerStatus.ALL_IN)
        player2 = PlayerState(seat_id=2, stack=0, committed_total=200, status=PlayerStatus.ALL_IN)

        state.seats[0] = player0
        state.seats[1] = player1
        state.seats[2] = player2

        pots = build_side_pots(state)

        # Should create:
        # Pot 0: 200 * 3 = 600 (all eligible)
        # Pot 1: 300 * 2 = 600 (player0 and player1)
        # Pot 2: 500 * 1 = 500 (only player0)
        assert len(pots) == 3

        assert pots[0].amount == 600  # 200 * 3
        assert pots[0].eligible_seats == {0, 1, 2}

        assert pots[1].amount == 600  # (500 - 200) * 2 = 300 * 2
        assert pots[1].eligible_seats == {0, 1}

        assert pots[2].amount == 500  # (1000 - 500) * 1 = 500 * 1
        assert pots[2].eligible_seats == {0}

        assert validate_pot_invariant(state, pots)
        total_committed = 1000 + 500 + 200
        total_pots = 600 + 600 + 500
        assert total_committed == total_pots

    def test_folded_players_excluded(self):
        """Test that folded players are excluded from pots."""
        state = GameState(num_seats=6)
        player0 = PlayerState(seat_id=0, stack=0, committed_total=1000, status=PlayerStatus.ALL_IN)
        player1 = PlayerState(seat_id=1, stack=0, committed_total=500, status=PlayerStatus.FOLDED)
        player2 = PlayerState(seat_id=2, stack=0, committed_total=500, status=PlayerStatus.ACTIVE)

        state.seats[0] = player0
        state.seats[1] = player1
        state.seats[2] = player2

        pots = build_side_pots(state)

        # Folded player should not be in any pot
        for pot in pots:
            assert 1 not in pot.eligible_seats

        # Only active players
        assert validate_pot_invariant(state, pots)
        # Only player0 and player2 contribute (player1 folded)
        total_committed = 1000 + 500
        total_pots = sum(pot.amount for pot in pots)
        assert total_committed == total_pots

    def test_empty_pots_no_active_players(self):
        """Test that no pots are created if no active players."""
        state = GameState(num_seats=6)
        player0 = PlayerState(seat_id=0, stack=0, committed_total=100, status=PlayerStatus.FOLDED)
        state.seats[0] = player0

        pots = build_side_pots(state)

        assert len(pots) == 0

    def test_single_player_pot(self):
        """Test pot with single player (shouldn't happen but test edge case)."""
        state = GameState(num_seats=6)
        player0 = PlayerState(seat_id=0, stack=0, committed_total=1000, status=PlayerStatus.ACTIVE)
        state.seats[0] = player0

        pots = build_side_pots(state)

        assert len(pots) == 1
        assert pots[0].amount == 1000
        assert pots[0].eligible_seats == {0}
        assert validate_pot_invariant(state, pots)


class TestPotDistribution:
    """Test pot distribution calculation."""

    def test_pot_distribution(self):
        """Test getting pot distribution for players."""
        state = GameState(num_seats=6)
        player0 = PlayerState(seat_id=0, stack=0, committed_total=1000, status=PlayerStatus.ALL_IN)
        player1 = PlayerState(seat_id=1, stack=0, committed_total=500, status=PlayerStatus.ALL_IN)
        player2 = PlayerState(seat_id=2, stack=500, committed_total=500, status=PlayerStatus.ACTIVE)

        state.seats[0] = player0
        state.seats[1] = player1
        state.seats[2] = player2

        distribution = get_pot_distribution(state)

        # Player 0 eligible for both pots
        assert distribution[0] == [0, 1]
        # Player 1 eligible only for main pot
        assert distribution[1] == [0]
        # Player 2 eligible only for main pot
        assert distribution[2] == [0]


class TestPotInvariant:
    """Test pot invariant validation."""

    def test_invariant_holds(self):
        """Test that invariant holds for valid pots."""
        state = GameState(num_seats=6)
        player0 = PlayerState(seat_id=0, stack=0, committed_total=1000, status=PlayerStatus.ALL_IN)
        player1 = PlayerState(seat_id=1, stack=0, committed_total=500, status=PlayerStatus.ALL_IN)
        state.seats[0] = player0
        state.seats[1] = player1

        pots = build_side_pots(state)
        assert validate_pot_invariant(state, pots)

    def test_invariant_fails_wrong_amount(self):
        """Test that invariant fails if pots don't match commitments."""
        state = GameState(num_seats=6)
        player0 = PlayerState(seat_id=0, stack=0, committed_total=1000, status=PlayerStatus.ALL_IN)
        player1 = PlayerState(seat_id=1, stack=0, committed_total=500, status=PlayerStatus.ALL_IN)
        state.seats[0] = player0
        state.seats[1] = player1

        pots = build_side_pots(state)
        # Corrupt a pot amount
        pots[0].amount = 999

        assert not validate_pot_invariant(state, pots)
