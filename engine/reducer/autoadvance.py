"""Auto-advance logic: automatic game progression after actions.

This module handles automatic transitions:
- Award pot if only one active player
- Deal next street if betting round complete
- Fast-forward dealing if everyone all-in
"""

from __future__ import annotations

from engine.domain.events import DomainEvent, HandEnded, StreetDealt
from engine.domain.state import GameState, PlayerStatus, Street
from engine.domain.types import Card
from engine.rules.legality import is_betting_round_complete
from engine.rules.sidepots import build_side_pots


def check_auto_advance(state: GameState, deck: object) -> tuple[GameState, list[DomainEvent]]:
    """Check if game should auto-advance and return new state + events.

    Args:
        state: Current game state
        deck: Deck instance for dealing cards

    Returns:
        Tuple of (new_state, events_list)
    """
    events = []
    current_state = state

    # Check if only one active player (everyone else folded)
    active_count = state.count_active_players()
    if active_count <= 1 and state.street != Street.COMPLETE:
        # Award pot to remaining player
        winner_seat = None
        for seat_id, player in enumerate(state.seats):
            if player is not None and player.status != PlayerStatus.FOLDED:
                winner_seat = seat_id
                break

        if winner_seat is not None:
            # Build pots and award to winner
            pots = build_side_pots(state)
            total_winnings = sum(pot.amount for pot in pots if winner_seat in pot.eligible_seats)

            # Award chips
            from engine.domain.events import ShowdownResolved
            from engine.reducer.reducer import apply_event

            event = ShowdownResolved(
                timestamp=0.0,  # Will be set by caller
                winners={winner_seat: total_winnings},
            )
            current_state = apply_event(current_state, event)
            events.append(event)

            # End hand
            end_event = HandEnded(
                timestamp=0.0,  # Will be set by caller
                winner_seat=winner_seat,
                reason="FOLD",
            )
            current_state = apply_event(current_state, end_event)
            events.append(end_event)

            return current_state, events

    # Check if betting round is complete
    if is_betting_round_complete(current_state) and current_state.street != Street.COMPLETE:
        # Check if everyone is all-in
        all_all_in = all(
            player is None
            or player.status == PlayerStatus.ALL_IN
            or player.status == PlayerStatus.FOLDED
            for player in current_state.seats
        )

        if all_all_in and current_state.street in (Street.PREFLOP, Street.FLOP, Street.TURN):
            # Fast-forward: deal remaining streets
            return _fast_forward_dealing(current_state, deck, events)

        # Normal progression: deal next street or go to showdown
        next_street = _get_next_street(current_state.street)
        if next_street == Street.SHOWDOWN:
            # Go to showdown
            return _resolve_showdown(current_state, events)
        else:
            # Deal next street
            return _advance_to_next_street(current_state, deck, events)

    return current_state, events


def _fast_forward_dealing(
    state: GameState, deck: object, events: list[DomainEvent]
) -> tuple[GameState, list[DomainEvent]]:
    """Fast-forward dealing remaining streets when everyone is all-in."""
    from engine.reducer.reducer import apply_event

    current_state = state
    current_events = list(events)

    # Deal remaining streets
    streets_to_deal = []
    if state.street == Street.PREFLOP:
        streets_to_deal = [Street.FLOP, Street.TURN, Street.RIVER]
    elif state.street == Street.FLOP:
        streets_to_deal = [Street.TURN, Street.RIVER]
    elif state.street == Street.TURN:
        streets_to_deal = [Street.RIVER]

    for street in streets_to_deal:
        cards = _deal_street_cards(deck, street)
        event = StreetDealt(
            timestamp=0.0,  # Will be set by caller
            street=street,
            cards=cards,
        )
        current_state = apply_event(current_state, event)
        current_events.append(event)

    # After fast-forward, go to showdown
    return current_state, current_events


def _advance_to_next_street(
    state: GameState, deck: object, events: list[DomainEvent]
) -> tuple[GameState, list[DomainEvent]]:
    """Advance to next street."""
    from engine.reducer.reducer import apply_event

    current_state = state
    current_events = list(events)

    # Determine next street
    next_street = _get_next_street(state.street)

    # Deal next street
    cards = _deal_street_cards(deck, next_street)
    event = StreetDealt(
        timestamp=0.0,  # Will be set by caller
        street=next_street,
        cards=cards,
    )
    current_state = apply_event(current_state, event)
    current_events.append(event)

    return current_state, current_events


def _resolve_showdown(
    state: GameState, events: list[DomainEvent]
) -> tuple[GameState, list[DomainEvent]]:
    """Resolve showdown by evaluating hands and splitting pots."""
    from engine.domain.events import ShowdownResolved
    from engine.reducer.reducer import apply_event

    current_state = state
    current_events = list(events)

    # Get active players with their hole cards
    # Note: In real implementation, hole cards would come from server state
    # For now, we'll need to handle this differently
    # This is a placeholder - actual implementation needs hole cards from state

    # Build side pots
    pots = build_side_pots(current_state)

    # For now, if we don't have hole cards, we can't evaluate
    # This will be handled properly when we integrate with server
    # For testing, we'll create a simple winner determination

    # Get active players (not folded)
    active_players = {}
    for seat_id, player in enumerate(current_state.seats):
        if player is not None and player.status != PlayerStatus.FOLDED:
            # In real implementation, we'd get hole_cards from player.hole_cards
            # For now, we'll skip hand evaluation and just split pots evenly
            active_players[seat_id] = None  # Placeholder

    # If we have hole cards, evaluate hands
    # Otherwise, split pots evenly (fallback for testing)
    if active_players:
        # Simple split: divide pots evenly among active players
        total_pot = sum(pot.amount for pot in pots)
        amount_per_player = total_pot // len(active_players)
        remainder = total_pot % len(active_players)

        winners = {}
        for i, seat_id in enumerate(active_players.keys()):
            amount = amount_per_player
            if i < remainder:
                amount += 1
            winners[seat_id] = amount
    else:
        winners = {}

    # Create showdown event
    event = ShowdownResolved(
        timestamp=0.0,  # Will be set by caller
        winners=winners,
    )
    current_state = apply_event(current_state, event)
    current_events.append(event)

    # End hand
    from engine.domain.events import HandEnded

    end_event = HandEnded(
        timestamp=0.0,  # Will be set by caller
        winner_seat=None if len(winners) > 1 else next(iter(winners.keys())) if winners else None,
        reason="SHOWDOWN",
    )
    current_state = apply_event(current_state, end_event)
    current_events.append(end_event)

    return current_state, current_events


def _get_next_street(current_street: Street) -> Street:
    """Get next street in sequence."""
    street_sequence = {
        Street.PREFLOP: Street.FLOP,
        Street.FLOP: Street.TURN,
        Street.TURN: Street.RIVER,
        Street.RIVER: Street.SHOWDOWN,
    }
    return street_sequence.get(current_street, Street.SHOWDOWN)


def _deal_street_cards(deck: object, street: Street) -> tuple[Card, ...]:
    """Deal cards for a street."""
    if street == Street.FLOP:
        return tuple(deck.deal(3))
    elif street in (Street.TURN, Street.RIVER):
        return tuple(deck.deal(1))
    else:
        return tuple()
