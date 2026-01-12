"""Pure reducer: next(state, command) -> (new_state, events[]).

The reducer is PURE - no IO, no side effects, no randomness (except via seed).
All state transitions go through the reducer, which validates commands and
emits events. State is derived by applying events in order.
"""

from __future__ import annotations

import time

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
from engine.reducer.autoadvance import check_auto_advance
from engine.rules.legality import (
    calculate_action_amount,
    get_call_amount,
    is_betting_round_complete,
    is_raise_reopening,
    next_player_to_act,
    validate_action,
)


def next_state(
    state: GameState, command: Command, deck: object | None = None
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
        return _handle_start_hand(state, command, timestamp, deck=deck)
    elif isinstance(command, RevealSeed):
        return _handle_reveal_seed(state, command, timestamp)
    elif isinstance(command, Act):
        return _handle_act(state, command, timestamp, deck)
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

    # Enforce 6 player max per table
    seated_count = sum(1 for seat in state.seats if seat is not None)
    if seated_count >= 6:
        raise ValueError("Table is full (max 6 players). Please join a different table.")

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
    state: GameState, command: StartHand, timestamp: float, deck: object | None = None
) -> tuple[GameState, list[DomainEvent]]:
    """Handle StartHand command."""
    if state.street != Street.WAITING:
        raise ValueError(f"Cannot start hand: current street is {state.street}")

    # Count seated players (any non-null seat)
    # Before hand starts, all seated players should have status ACTIVE
    seated_players = [p for p in state.seats if p is not None]
    if len(seated_players) < 2:
        raise ValueError("Need at least 2 seated players to start hand")

    # Find active players for button/blind assignment
    # Filter for ACTIVE status (should be all seated players, but check anyway)
    active_seats = [
        i
        for i, player in enumerate(state.seats)
        if player is not None and player.status == PlayerStatus.ACTIVE
    ]

    # Use seated_players count, but active_seats for positions (they should match)
    if len(active_seats) < 2:
        raise ValueError(
            f"Need at least 2 active players to start hand (found {len(active_seats)} active out of {len(seated_players)} seated)"
        )

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
    events = [event]

    # SIMPLE: Deal hole cards directly to players if deck is provided
    if deck is not None:
        updated_seats = list(new_state.seats)
        for seat_id in active_seats:
            hole_cards = deck.deal(2)  # Deal 2 cards
            player = updated_seats[seat_id]
            if player is not None:
                # Update player with hole cards
                updated_seats[seat_id] = player.model_copy(update={"hole_cards": tuple(hole_cards)})
                # Create event for logging
                cards_event = CardsDealt(timestamp=timestamp, seat_id=seat_id)
                events.append(cards_event)
                print(f"[Reducer] Dealt cards to seat {seat_id}: {hole_cards[0]}, {hole_cards[1]}")
        new_state = new_state.model_copy(update={"seats": updated_seats})
        print(f"[Reducer] Dealt cards to {len(active_seats)} players")

    # Post blinds
    from engine.domain.events import BlindPosted

    sb_event = BlindPosted(
        timestamp=timestamp, seat_id=sb_seat, amount=state.small_blind, blind_type="SB"
    )
    new_state = apply_event(new_state, sb_event)
    events.append(sb_event)

    bb_event = BlindPosted(
        timestamp=timestamp, seat_id=bb_seat, amount=state.big_blind, blind_type="BB"
    )
    new_state = apply_event(new_state, bb_event)
    events.append(bb_event)

    # Set initial to_act_seat (after BB, action starts with UTG)
    if len(active_seats) > 2:
        to_act_seat = active_seats[3 % len(active_seats)]
    else:
        to_act_seat = button_seat  # Heads-up: button acts first
    new_state = new_state.model_copy(update={"to_act_seat": to_act_seat})

    return new_state, events


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
    state: GameState, command: Act, timestamp: float, deck: object | None = None
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
    else:
        # No one needs to act - set to_act_seat to None to indicate betting is complete
        new_state = new_state.model_copy(update={"to_act_seat": None})
        print(f"[Reducer] No next player to act after action by seat {command.seat_id}")

    # Check if betting round is complete
    events = [event]
    betting_complete = is_betting_round_complete(new_state)
    print(f"[Reducer] After action: street={new_state.street.value}, betting_complete={betting_complete}, deck={deck is not None}, to_act_seat={new_state.to_act_seat}, next_seat={next_seat}")
    
    if betting_complete:
        events.append(BettingRoundComplete(timestamp=timestamp, street=new_state.street))
        print(f"[Reducer] Betting round complete for {new_state.street.value}, added BettingRoundComplete event")

    # Auto-advance: check if game should progress automatically
    # Note: We pass the state BEFORE applying BettingRoundComplete, as check_auto_advance checks is_betting_round_complete internally
    if deck is not None:
        # Set timestamps for auto-advance events
        advance_state, advance_events = check_auto_advance(new_state, deck)
        # Update timestamps (events are frozen, recreate with correct timestamp)
        from dataclasses import replace

        if advance_events:
            print(f"[Reducer] Auto-advance triggered: {len(advance_events)} events, new street={advance_state.street.value}")
            advance_events = [replace(e, timestamp=timestamp) for e in advance_events]
            new_state = advance_state
            events.extend(advance_events)
        else:
            print(f"[Reducer] Auto-advance did not trigger (no events)")
    else:
        if betting_complete:
            print(f"[Reducer] WARNING: Betting round complete but deck is None - cannot auto-advance!")

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
            player_id=event.player_id,
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
                "last_hand_results": None,  # Clear previous hand results when starting new hand
            }
        )

    elif isinstance(event, SeedRevealed):
        return state.model_copy(update={"seed_reveal": event.seed_reveal})

    elif isinstance(event, CardsDealt):
        # Store hole cards in player state
        # Note: Cards are passed via the deck, not in the event (for security)
        # The caller must update hole_cards after creating CardsDealt event
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

        # Append new community cards to existing ones (don't replace!)
        # FLOP adds 3 cards, TURN adds 1, RIVER adds 1
        existing_cards = list(state.community_cards)
        new_cards = list(event.cards)
        all_community_cards = existing_cards + new_cards

        return state.model_copy(
            update={
                "street": event.street,
                "community_cards": all_community_cards,
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
        # Award chips to winners and reset committed amounts
        updated_seats = []
        for i, seat in enumerate(new_seats):
            if seat is not None:
                winnings = event.winners.get(i, 0)
                if winnings > 0:
                    # Award chips and reset committed amounts
                    updated_seats.append(
                        seat.model_copy(update={
                            "stack": seat.stack + winnings,
                            "committed_total": 0,
                            "committed_street": 0,
                        })
                    )
                    print(f"[Reducer] Awarded {winnings} chips to seat {i} (new stack: {seat.stack + winnings})")
                else:
                    # Reset committed amounts even if no winnings
                    updated_seats.append(
                        seat.model_copy(update={
                            "committed_total": 0,
                            "committed_street": 0,
                        })
                    )
            else:
                updated_seats.append(seat)
        
        # Clear pots after chips have been awarded
        # Store winners in state for results display
        return state.model_copy(update={"seats": updated_seats, "pots": [], "last_hand_results": event.winners})

    elif isinstance(event, HandEnded):
        # Reset table state for a new hand
        updated_seats = []
        for seat in new_seats:
            if seat is not None:
                # Determine new status:
                # - If player has chips, they're ACTIVE for next hand
                # - If player has 0 chips, they're OUT (busted)
                # - Otherwise keep their status (shouldn't happen)
                if seat.stack > 0:
                    new_status = PlayerStatus.ACTIVE
                else:
                    new_status = PlayerStatus.OUT
                    print(f"[Reducer] Seat {seat.seat_id} busted (0 chips), setting status to OUT")
                
                # Reset player state: clear committed amounts, reset status, clear hole cards
                updated_seats.append(
                    seat.model_copy(update={
                        "committed_total": 0,
                        "committed_street": 0,
                        "acted_this_street": False,
                        "status": new_status,
                        "hole_cards": None,  # Clear hole cards for security
                    })
                )
            else:
                updated_seats.append(seat)
        
        # Reset all hand-specific state (but preserve last_hand_results for display)
        print(f"[Reducer] Hand ended: resetting table state for new hand")
        return state.model_copy(update={
            "street": Street.WAITING,  # Reset to WAITING so a new hand can start
            "hand_id": None,
            "seed_commit": None,
            "seed_reveal": None,
            "current_bet": 0,
            "min_raise": 0,
            "last_raiser_seat": None,
            "to_act_seat": None,
            "community_cards": [],
            "pots": [],
            "seats": updated_seats,
            # Keep last_hand_results for results display - will be cleared on new hand start
        })

    # Unknown event type - return state unchanged
    return state
