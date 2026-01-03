"""Pure reducer: next(state, command) -> (new_state, events[]).

The reducer is PURE - no IO, no side effects, no randomness (except via seed).
All state transitions go through the reducer, which validates commands and
emits events. State is derived by applying events in order.
"""

from __future__ import annotations

import time
from typing import Optional

from engine.domain.commands import Act, ActionType, Command, RevealSeed, SitDown, StandUp, StartHand
from engine.domain.events import (
    ActionApplied,
    BettingRoundComplete,
    BlindPosted,
    CardsDealt,
    DomainEvent,
    HandEnded,
    HandStarted,
    PlayerSatDown,
    PlayerStoodUp,
    PotCreated,
    SeedRevealed,
    ShowdownResolved,
    StreetDealt,
)
from engine.domain.state import GameState, PlayerStatus, Street
from engine.domain.types import Money, SeatId
from engine.rules.legality import (
    calculate_action_amount,
    get_call_amount,
    get_min_raise_amount,
    is_betting_round_complete,
    is_raise_reopening,
    next_player_to_act,
    validate_action,
)


def next_state(
    state: GameState, command: Command, deck: Optional[object] = None
) -> tuple[GameState, list[DomainEvent]]:
    """Process a command and return new state + events.

    This is the main reducer function. It validates the command, applies
    business logic, and emits events. The reducer is PURE - no IO.

    Args:
        state: Current game state
        command: Command to process
        deck: Optional deck for dealing cards (used internally)

    Returns:
        Tuple of (new_state, events_list)

    Raises:
        ValueError: If command is invalid for current state
    """
    timestamp = time.time()

    if isinstance(command, SitDown):
        return _handle_sit_down(state, command, timestamp)
    elif isinstance(command, StandUp):
        return _handle_stand_up(state, command, timestamp)
    elif isinstance(command, StartHand):
        return _handle_start_hand(state, command, timestamp)
    elif isinstance(command, RevealSeed):
        return _handle_reveal_seed(state, command, timestamp)
    elif isinstance(command, Act):
        return _handle_act(state, command, timestamp)
    else:
        raise ValueError(f"Unknown command type: {type(command)}")


def _handle_sit_down(
    state: GameState, command: SitDown, timestamp: float
) -> tuple[GameState, list[DomainEvent]]:
    """Handle SitDown command."""
    if command.seat_id < 0 or command.seat_id >= state.num_seats:
        raise ValueError(f"Invalid seat_id: {command.seat_id}")
    if state.seats[command.seat_id] is not None:
        raise ValueError(f"Seat {command.seat_id} is already occupied")
    if command.stack <= 0:
        raise ValueError("Stack must be positive")

    event = PlayerSatDown(
        timestamp=timestamp,
        seat_id=command.seat_id,
        player_id=command.player_id,
        stack=command.stack,
    )

    new_state = apply_event(state, event)
    return new_state, [event]


def _handle_stand_up(
    state: GameState, command: StandUp, timestamp: float
) -> tuple[GameState, list[DomainEvent]]:
    """Handle StandUp command."""
    if command.seat_id < 0 or command.seat_id >= state.num_seats:
        raise ValueError(f"Invalid seat_id: {command.seat_id}")
    if state.seats[command.seat_id] is None:
        raise ValueError(f"Seat {command.seat_id} is empty")

    event = PlayerStoodUp(timestamp=timestamp, seat_id=command.seat_id)

    new_state = apply_event(state, event)
    return new_state, [event]


def _handle_start_hand(
    state: GameState, command: StartHand, timestamp: float
) -> tuple[GameState, list[DomainEvent]]:
    """Handle StartHand command."""
    if state.street != Street.WAITING:
        raise ValueError(f"Cannot start hand: current street is {state.street}")
    if state.count_active_players() < 2:
        raise ValueError("Need at least 2 active players to start hand")

    # Find active players and assign positions
    active_seats = [
        i for i, player in enumerate(state.seats) if player is not None and player.status == PlayerStatus.ACTIVE
    ]

    if len(active_seats) < 2:
        raise ValueError("Need at least 2 active players")

    # Simple button rotation (for now, just use first active seat)
    # TODO: Proper button rotation in Phase 5
    button_seat = active_seats[0]
    sb_seat = active_seats[1 % len(active_seats)]
    bb_seat = active_seats[2 % len(active_seats)]

    event = HandStarted(
        timestamp=timestamp,
        hand_id=command.hand_id,
        button_seat=button_seat,
        sb_seat=sb_seat,
        bb_seat=bb_seat,
        seed_commit=command.seed_commit,
    )

    new_state = apply_event(state, event)
    # Set initial to_act_seat (after BB, action starts with UTG)
    # For now, set to first active seat after BB
    if len(active_seats) > 2:
        to_act_seat = active_seats[3 % len(active_seats)]
    else:
        to_act_seat = button_seat  # Heads-up: button acts first
    new_state = new_state.model_copy(update={"to_act_seat": to_act_seat})
    return new_state, [event]


def _handle_reveal_seed(
    state: GameState, command: RevealSeed, timestamp: float
) -> tuple[GameState, list[DomainEvent]]:
    """Handle RevealSeed command."""
    if state.seed_commit is None:
        raise ValueError("No seed commit found - hand not started")
    if state.seed_reveal is not None:
        raise ValueError("Seed already revealed")

    event = SeedRevealed(timestamp=timestamp, seed_reveal=command.seed_reveal)

    new_state = apply_event(state, event)
    return new_state, [event]


def _handle_act(
    state: GameState, command: Act, timestamp: float
) -> tuple[GameState, list[DomainEvent]]:
    """Handle Act command with full legality validation."""
    # Validate action
    is_valid, error_msg = validate_action(
        state, command.seat_id, command.action_type, command.amount
    )
    if not is_valid:
        raise ValueError(error_msg)

    player = state.get_player(command.seat_id)
    assert player is not None  # validate_action ensures this

    # Calculate actual amount to commit
    chips_committed = calculate_action_amount(
        state, command.seat_id, command.action_type, command.amount
    )

    new_stack = player.stack - chips_committed

    # Calculate new min_raise and last_raiser_seat before creating event
    new_min_raise = state.min_raise
    new_last_raiser_seat = state.last_raiser_seat

    if command.action_type == ActionType.BET:
        # First bet of the street
        new_min_raise = chips_committed  # Next raise must be at least this amount
        new_last_raiser_seat = command.seat_id
    elif command.action_type == ActionType.RAISE:
        # Calculate raise increment
        call_amount = get_call_amount(state, command.seat_id)
        raise_increment = chips_committed - call_amount
        if is_raise_reopening(state, chips_committed, new_stack):
            new_min_raise = raise_increment
            new_last_raiser_seat = command.seat_id

    # Create event
    event = ActionApplied(
        timestamp=timestamp,
        seat_id=command.seat_id,
        action_type=command.action_type.value,
        amount=command.amount,
        chips_committed=chips_committed,
        new_stack=new_stack,
    )

    new_state = apply_event(state, event)

    # Update min_raise and last_raiser_seat if needed
    if new_min_raise != state.min_raise or new_last_raiser_seat != state.last_raiser_seat:
        new_state = new_state.model_copy(
            update={
                "min_raise": new_min_raise,
                "last_raiser_seat": new_last_raiser_seat,
            }
        )

    # Update to_act_seat to next player
    next_seat = next_player_to_act(new_state)
    if next_seat is not None:
        new_state = new_state.model_copy(update={"to_act_seat": next_seat})

    # Check if betting round is complete
    events = [event]
    if is_betting_round_complete(new_state):
        events.append(
            BettingRoundComplete(timestamp=timestamp, street=new_state.street)
        )

    return new_state, events


def apply_event(state: GameState, event: DomainEvent) -> GameState:
    """Apply a single event to state, returning new state.

    This is the event handler. It's PURE and deterministic.
    Given the same state and event, it always produces the same new state.

    Args:
        state: Current state
        event: Event to apply

    Returns:
        New state with event applied
    """
    from engine.domain.state import PlayerState

    # Create a mutable copy of seats
    new_seats = list(state.seats)

    if isinstance(event, PlayerSatDown):
        player = PlayerState(
            seat_id=event.seat_id,
            stack=event.stack,
            status=PlayerStatus.ACTIVE,
        )
        new_seats[event.seat_id] = player
        return state.model_copy(update={"seats": new_seats})

    elif isinstance(event, PlayerStoodUp):
        new_seats[event.seat_id] = None
        return state.model_copy(update={"seats": new_seats})

    elif isinstance(event, HandStarted):
        # Reset player committed amounts
        updated_seats = []
        for seat in new_seats:
            if seat is not None:
                updated_seats.append(
                    seat.model_copy(
                        update={
                            "committed_street": 0,
                            "committed_total": 0,
                            "acted_this_street": False,
                        }
                    )
                )
            else:
                updated_seats.append(None)

        return state.model_copy(
            update={
                "hand_id": event.hand_id,
                "street": Street.PREFLOP,
                "button_seat": event.button_seat,
                "sb_seat": event.sb_seat,
                "bb_seat": event.bb_seat,
                "seed_commit": event.seed_commit,
                "current_bet": 0,
                "min_raise": 0,
                "last_raiser_seat": None,
                "pots": [],
                "community_cards": [],
                "seats": updated_seats,
            }
        )

    elif isinstance(event, SeedRevealed):
        return state.model_copy(update={"seed_reveal": event.seed_reveal})

    elif isinstance(event, CardsDealt):
        # Cards are server-only, so we don't modify state here
        # This event is mainly for logging/hand history
        return state

    elif isinstance(event, BlindPosted):
        seat_idx = event.seat_id
        if new_seats[seat_idx] is not None:
            player = new_seats[seat_idx]
            blind_amount = min(event.amount, player.stack)
            updated_player = player.model_copy(
                update={
                    "stack": player.stack - blind_amount,
                    "committed_street": blind_amount,
                    "committed_total": blind_amount,
                }
            )
            new_seats[seat_idx] = updated_player
            new_current_bet = max(state.current_bet, blind_amount)
            return state.model_copy(update={"seats": new_seats, "current_bet": new_current_bet})
        return state

    elif isinstance(event, ActionApplied):
        seat_idx = event.seat_id
        if new_seats[seat_idx] is not None:
            player = new_seats[seat_idx]
            new_status = player.status
            if event.action_type == "FOLD":
                new_status = PlayerStatus.FOLDED
            elif event.new_stack == 0:
                new_status = PlayerStatus.ALL_IN

            updated_player = player.model_copy(
                update={
                    "stack": event.new_stack,
                    "committed_street": player.committed_street + event.chips_committed,
                    "committed_total": player.committed_total + event.chips_committed,
                    "acted_this_street": True,
                    "status": new_status,
                }
            )
            new_seats[seat_idx] = updated_player

            # Update betting state
            updates = {"seats": new_seats}
            if event.action_type in ("BET", "RAISE"):
                new_current_bet = updated_player.committed_street
                updates["current_bet"] = new_current_bet
                # min_raise and last_raiser_seat are handled in reducer

            return state.model_copy(update=updates)
        return state

    elif isinstance(event, StreetDealt):
        # Reset acted_this_street and committed_street for active players
        updated_seats = []
        for seat in new_seats:
            if seat is not None and seat.status in (PlayerStatus.ACTIVE, PlayerStatus.ALL_IN):
                updated_seats.append(
                    seat.model_copy(
                        update={
                            "committed_street": 0,
                            "acted_this_street": False,
                        }
                    )
                )
            else:
                updated_seats.append(seat)

        return state.model_copy(
            update={
                "street": event.street,
                "community_cards": list(event.cards),
                "current_bet": 0,
                "min_raise": 0,
                "last_raiser_seat": None,
                "seats": updated_seats,
            }
        )

    elif isinstance(event, BettingRoundComplete):
        # No state change needed - this is informational
        return state

    elif isinstance(event, PotCreated):
        from engine.domain.state import Pot

        new_pots = list(state.pots)
        pot = Pot(amount=event.amount, eligible_seats=set(event.eligible_seats))
        if event.pot_index < len(new_pots):
            new_pots[event.pot_index] = pot
        else:
            new_pots.append(pot)
        return state.model_copy(update={"pots": new_pots})

    elif isinstance(event, ShowdownResolved):
        # Award chips to winners
        updated_seats = []
        for i, seat in enumerate(new_seats):
            if seat is not None and i in event.winners:
                updated_seats.append(
                    seat.model_copy(update={"stack": seat.stack + event.winners[i]})
                )
            else:
                updated_seats.append(seat)
        return state.model_copy(update={"seats": updated_seats})

    elif isinstance(event, HandEnded):
        return state.model_copy(update={"street": Street.COMPLETE})

    # Unknown event type - return state unchanged
    return state

