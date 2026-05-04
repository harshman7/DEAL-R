"""Game state invariants.

Invariants are properties that must always hold true for valid game states.
These are checked in property-based tests to ensure correctness.
"""

from __future__ import annotations

from engine.domain.state import GameState, PlayerStatus, Street
from engine.rules.sidepots import build_side_pots, validate_pot_invariant

_POT_VIOLATION = "Pot invariant violated: sum(pots) != sum(committed_total) at terminal state"


def _negative_stack_violations(state: GameState) -> list[str]:
    violations: list[str] = []
    for seat_id, player in enumerate(state.seats):
        if player is None:
            continue
        if player.stack < 0:
            violations.append(f"Player at seat {seat_id} has negative stack: {player.stack}")
        if player.committed_street < 0:
            violations.append(
                f"Player at seat {seat_id} has negative committed_street: {player.committed_street}"
            )
        if player.committed_total < 0:
            violations.append(
                f"Player at seat {seat_id} has negative committed_total: {player.committed_total}"
            )
    return violations


def check_all_invariants(state: GameState) -> list[str]:
    """Check all invariants and return list of violations.

    Args:
        state: Game state to check

    Returns:
        List of invariant violation messages (empty if all pass)
    """
    violations: list[str] = []
    violations.extend(_negative_stack_violations(state))

    # Chip conservation (vs initial_total) is checked in property tests via check_chip_conservation.

    if state.street in (Street.SHOWDOWN, Street.COMPLETE) and not check_pot_correctness(state):
        violations.append(_POT_VIOLATION)

    if state.current_bet < 0:
        violations.append(f"current_bet is negative: {state.current_bet}")
    if state.min_raise < 0:
        violations.append(f"min_raise is negative: {state.min_raise}")

    for seat_id, player in enumerate(state.seats):
        if player is not None:
            if player.stack == 0 and player.status == PlayerStatus.ACTIVE:
                if player.committed_total > 0:
                    violations.append(
                        f"Player at seat {seat_id} has stack=0 but status=ACTIVE "
                        "(should be ALL_IN)"
                    )

    return violations


def check_chip_conservation(initial_total: int, current_state: GameState) -> bool:
    """Check that total chips are conserved.

    Args:
        initial_total: Initial total chips on table
        current_state: Current game state

    Returns:
        True if chips are conserved, False otherwise
    """
    current_total = sum(
        (player.stack + player.committed_total)
        for player in current_state.seats
        if player is not None
    )
    return current_total == initial_total


def check_no_negative_stacks(state: GameState) -> bool:
    """Check that no player has negative stack.

    Args:
        state: Game state to check

    Returns:
        True if no negative stacks, False otherwise
    """
    return not _negative_stack_violations(state)


def check_pot_correctness(state: GameState) -> bool:
    """Check that pots match committed chips at terminal state.

    Args:
        state: Game state to check

    Returns:
        True if pots are correct, False otherwise
    """
    if state.street not in (Street.SHOWDOWN, Street.COMPLETE):
        return True  # Not at terminal state yet

    pots = build_side_pots(state)
    return validate_pot_invariant(state, pots)
