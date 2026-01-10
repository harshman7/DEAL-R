"""Deterministic side pot builder.

This module calculates side pots based on player commitments.
The algorithm is deterministic and handles multiple all-ins correctly.
"""

from __future__ import annotations

from engine.domain.state import GameState, PlayerStatus, Pot
from engine.domain.types import SeatId


def build_side_pots(state: GameState) -> list[Pot]:
    """Build side pots from player commitments.

    Creates layered pots based on committed_total for each player.
    Players who went all-in at different amounts create side pots.

    Algorithm:
    1. Get all active players (not folded) and their committed_total
    2. Sort unique commitment levels
    3. For each level, create a pot:
       - Amount = (level - previous_level) * eligible_players_count
       - Eligible = all players who committed >= this level

    Args:
        state: Current game state

    Returns:
        List of pots (main pot first, then side pots)

    Example:
        Player A: committed_total = 1000
        Player B: committed_total = 500
        Player C: committed_total = 500

        Creates:
        - Main pot: 500 * 3 = 1500 (all eligible)
        - Side pot: 500 * 1 = 500 (only A eligible)
        Total: 2000 (matches sum of committed_total)
    """
    # Get all players still in hand (not folded, not out)
    active_players = []
    for seat_id, player in enumerate(state.seats):
        if player is not None and player.status != PlayerStatus.FOLDED:
            active_players.append((seat_id, player.committed_total))

    if not active_players:
        return []

    # Get unique commitment levels, sorted ascending
    commitment_levels = sorted(set(committed for _, committed in active_players))

    pots = []
    previous_level = 0

    for level in commitment_levels:
        # Find eligible players (committed >= this level)
        eligible_seats = {seat_id for seat_id, committed in active_players if committed >= level}

        if not eligible_seats:
            continue

        # Calculate pot amount
        # Each eligible player contributes (level - previous_level)
        increment = level - previous_level
        pot_amount = increment * len(eligible_seats)

        if pot_amount > 0:
            pot = Pot(amount=pot_amount, eligible_seats=eligible_seats)
            pots.append(pot)

        previous_level = level

    return pots


def validate_pot_invariant(state: GameState, pots: list[Pot]) -> bool:
    """Validate that sum of pots equals sum of committed_total.

    This is a critical invariant: chips must be conserved.

    Args:
        state: Current game state
        pots: List of pots to validate

    Returns:
        True if invariant holds, False otherwise
    """
    total_committed = sum(
        player.committed_total
        for player in state.seats
        if player is not None and player.status != PlayerStatus.FOLDED
    )

    total_pots = sum(pot.amount for pot in pots)

    return total_committed == total_pots


def get_pot_distribution(state: GameState) -> dict[SeatId, list[int]]:
    """Get pot distribution showing which pots each player is eligible for.

    Args:
        state: Current game state

    Returns:
        Dict mapping seat_id -> list of pot indices player is eligible for
    """
    pots = build_side_pots(state)
    distribution = {}

    for seat_id, player in enumerate(state.seats):
        if player is None:
            continue

        eligible_pots = [i for i, pot in enumerate(pots) if seat_id in pot.eligible_seats]
        distribution[seat_id] = eligible_pots

    return distribution
