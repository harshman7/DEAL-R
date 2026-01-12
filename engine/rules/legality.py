"""Betting legality and round completion logic.

This module contains pure functions for:
- Computing legal actions for a player
- Calculating minimum raise amounts
- Determining if betting round is complete
- Finding next player to act
"""

from __future__ import annotations

from engine.domain.commands import ActionType
from engine.domain.state import GameState, PlayerStatus, Street
from engine.domain.types import Money, SeatId


def get_call_amount(state: GameState, seat_id: SeatId) -> Money:
    """Calculate the amount a player needs to call.

    Args:
        state: Current game state
        seat_id: Seat to calculate call amount for

    Returns:
        Amount needed to call (0 if already at current bet)
    """
    player = state.get_player(seat_id)
    if player is None:
        return 0

    call_amount = state.current_bet - player.committed_street
    return max(0, call_amount)


def get_min_raise_amount(state: GameState) -> Money:
    """Calculate minimum raise amount.

    Minimum raise is:
    - If no raise yet this street: big blind
    - If raise exists: 2x the last raise amount (difference between
      current_bet and the bet before the last raise)

    Args:
        state: Current game state

    Returns:
        Minimum raise amount
    """
    if state.current_bet == 0:
        # No betting yet - minimum raise is big blind
        return state.big_blind

    # Minimum raise is the difference between current bet and previous bet
    # For the first raise, previous bet is 0, so min_raise = current_bet
    # For subsequent raises, min_raise = current_bet - previous_bet
    # But we need at least big_blind as the minimum raise increment
    if state.min_raise == 0:
        # First raise of the street - minimum is big blind
        return state.big_blind
    else:
        # Subsequent raises - minimum is the last raise amount
        return state.min_raise


def is_raise_reopening(state: GameState, raise_amount: Money, player_stack: Money) -> bool:
    """Check if a raise amount would reopen betting.

    A raise reopens betting if:
    1. The raise amount >= minimum raise amount
    2. The player has enough chips to make a full raise (or goes all-in with >= min_raise)

    Args:
        state: Current game state
        raise_amount: Amount player wants to raise
        player_stack: Player's remaining stack

    Returns:
        True if raise would reopen betting, False otherwise
    """
    min_raise = get_min_raise_amount(state)
    total_raise = raise_amount

    # If player goes all-in, check if all-in amount >= min_raise
    if total_raise >= player_stack:
        # All-in - only reopens if all-in amount >= min_raise
        return player_stack >= min_raise

    # Full raise - must be >= min_raise
    return total_raise >= min_raise


def compute_legal_actions(state: GameState, seat_id: SeatId) -> set[ActionType]:
    """Compute legal actions for a player at the given seat.

    Args:
        state: Current game state
        seat_id: Seat to compute legal actions for

    Returns:
        Set of legal action types
    """
    player = state.get_player(seat_id)
    if player is None:
        return set()

    if player.status != PlayerStatus.ACTIVE:
        return set()

    if state.street == Street.WAITING or state.street == Street.COMPLETE:
        return set()

    legal_actions = set()
    call_amount = get_call_amount(state, seat_id)

    # FOLD is always legal (if there's a bet to fold to)
    if call_amount > 0:
        legal_actions.add(ActionType.FOLD)

    # CHECK is legal if call_amount == 0
    if call_amount == 0:
        legal_actions.add(ActionType.CHECK)

    # CALL is legal if call_amount > 0 and player has chips
    if call_amount > 0 and player.stack > 0:
        legal_actions.add(ActionType.CALL)

    # BET is legal on first action (current_bet == 0) and player has chips
    if state.current_bet == 0 and player.stack > 0:
        legal_actions.add(ActionType.BET)

    # RAISE is legal if there's a bet and player has chips
    if state.current_bet > 0 and player.stack > 0:
        legal_actions.add(ActionType.RAISE)

    return legal_actions


def validate_action(
    state: GameState,
    seat_id: SeatId,
    action_type: ActionType,
    amount: Money | None = None,
) -> tuple[bool, str]:
    """Validate if an action is legal and return (is_valid, error_message).

    Args:
        state: Current game state
        seat_id: Seat making the action
        action_type: Type of action
        amount: Amount for BET/RAISE (required for those actions)

    Returns:
        Tuple of (is_valid, error_message)
    """
    player = state.get_player(seat_id)
    if player is None:
        return False, f"No player at seat {seat_id}"

    if player.status != PlayerStatus.ACTIVE:
        return False, f"Player at seat {seat_id} is not active"

    legal_actions = compute_legal_actions(state, seat_id)
    if action_type not in legal_actions:
        return False, f"Action {action_type.value} is not legal for seat {seat_id}"

    call_amount = get_call_amount(state, seat_id)

    if action_type == ActionType.FOLD:
        if call_amount == 0:
            return False, "Cannot fold when no bet to call"
        return True, ""

    if action_type == ActionType.CHECK:
        if call_amount > 0:
            return False, "Cannot check when there's a bet to call"
        return True, ""

    if action_type == ActionType.CALL:
        if call_amount == 0:
            return False, "Cannot call when no bet to call"
        if player.stack < call_amount:
            # All-in call is valid
            return True, ""
        return True, ""

    if action_type == ActionType.BET:
        if amount is None:
            return False, "BET requires amount"
        if state.current_bet > 0:
            return False, "Cannot bet when there's already a bet (use RAISE)"
        if amount < state.big_blind:
            return False, f"Bet must be at least big blind ({state.big_blind})"
        if amount > player.stack:
            return False, "Bet amount exceeds stack"
        return True, ""

    if action_type == ActionType.RAISE:
        if amount is None:
            return False, "RAISE requires amount"
        if state.current_bet == 0:
            return False, "Cannot raise when no bet (use BET)"
        if amount > player.stack:
            return False, "Raise amount exceeds stack"

        # Calculate total raise amount (amount above current bet)
        call_amount = get_call_amount(state, seat_id)
        total_raise = amount - call_amount

        min_raise = get_min_raise_amount(state)
        if total_raise < min_raise and amount < player.stack:
            # Not a full raise and not all-in
            return False, f"Raise must be at least {min_raise} above call amount"

        return True, ""

    return False, f"Unknown action type: {action_type}"


def calculate_action_amount(
    state: GameState,
    seat_id: SeatId,
    action_type: ActionType,
    requested_amount: Money | None = None,
) -> Money:
    """Calculate the actual amount to commit for an action.

    Args:
        state: Current game state
        seat_id: Seat making the action
        action_type: Type of action
        requested_amount: Requested amount (for BET/RAISE)

    Returns:
        Actual amount to commit

    Raises:
        ValueError: If action is invalid
    """
    player = state.get_player(seat_id)
    if player is None:
        raise ValueError(f"No player at seat {seat_id}")

    call_amount = get_call_amount(state, seat_id)

    if action_type == ActionType.FOLD:
        return 0

    if action_type == ActionType.CHECK:
        return 0

    if action_type == ActionType.CALL:
        return min(call_amount, player.stack)

    if action_type == ActionType.BET:
        if requested_amount is None:
            raise ValueError("BET requires amount")
        return min(requested_amount, player.stack)

    if action_type == ActionType.RAISE:
        if requested_amount is None:
            raise ValueError("RAISE requires amount")
        # requested_amount is total amount to commit
        return min(requested_amount, player.stack)

    raise ValueError(f"Unknown action type: {action_type}")


def next_player_to_act(state: GameState) -> SeatId | None:
    """Find the next player who should act.

    Args:
        state: Current game state

    Returns:
        Seat ID of next player to act, or None if no one needs to act
    """
    if state.to_act_seat is None:
        return None

    if state.street in (Street.WAITING, Street.COMPLETE, Street.SHOWDOWN):
        return None

    # Start from to_act_seat and find next active player who hasn't acted
    start_seat = state.to_act_seat
    current_seat = start_seat
    checked_seats = set()

    while current_seat not in checked_seats:
        checked_seats.add(current_seat)
        player = state.get_player(current_seat)

        if player is not None and player.status == PlayerStatus.ACTIVE:
            if not player.acted_this_street:
                return current_seat

        # Move to next seat (wrap around)
        current_seat = (current_seat + 1) % state.num_seats

        # If we've checked all seats, no one needs to act
        if current_seat == start_seat:
            break

    return None


def is_betting_round_complete(state: GameState) -> bool:
    """Check if the current betting round is complete.

    A betting round is complete when:
    1. All active (non-folded, non-all-in) players have acted
    2. All active players have committed_street == current_bet
    3. Action has returned to last aggressor (or no aggressor exists)

    Args:
        state: Current game state

    Returns:
        True if betting round is complete, False otherwise
    """
    if state.street in (Street.WAITING, Street.COMPLETE, Street.SHOWDOWN):
        return False

    # If to_act_seat is None, betting is complete (no one needs to act)
    if state.to_act_seat is None:
        return True

    # Get all active players (not folded, not out)
    active_players = [
        (i, player)
        for i, player in enumerate(state.seats)
        if player is not None and player.status in (PlayerStatus.ACTIVE, PlayerStatus.ALL_IN)
    ]

    if len(active_players) <= 1:
        # Only one or zero active players - round is complete
        return True

    # Check if all active players have acted
    for seat_id, player in active_players:
        if player.status == PlayerStatus.ACTIVE and not player.acted_this_street:
            return False

    # Check if all active players are at the same commitment level
    # (or all-in with less)
    if state.current_bet == 0:
        # No betting - everyone checked
        return True

    # All active players should have committed_street == current_bet
    # (or be all-in with less)
    for seat_id, player in active_players:
        if player.status == PlayerStatus.ACTIVE:
            if player.committed_street < state.current_bet and player.stack > 0:
                # Player hasn't called yet
                return False

    # Check if action has returned to last aggressor
    if state.last_raiser_seat is not None:
        # Action should have returned to last raiser
        # If last raiser has acted again, round is complete
        last_raiser = state.get_player(state.last_raiser_seat)
        if last_raiser is not None and last_raiser.acted_this_street:
            return True

        # Check if we've gone around and no one can act
        # (all have acted or are all-in)
        return next_player_to_act(state) is None

    # No aggressor - round is complete if everyone has acted
    return next_player_to_act(state) is None
