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
    betting_complete = is_betting_round_complete(current_state)
    print(f"[AutoAdvance] Checking auto-advance: street={current_state.street.value}, betting_complete={betting_complete}, deck={deck is not None}")
    
    if betting_complete and current_state.street != Street.COMPLETE:
        # Check if everyone is all-in
        all_all_in = all(
            player is None
            or player.status == PlayerStatus.ALL_IN
            or player.status == PlayerStatus.FOLDED
            for player in current_state.seats
        )

        if all_all_in and current_state.street in (Street.PREFLOP, Street.FLOP, Street.TURN):
            # Fast-forward: deal remaining streets
            print(f"[AutoAdvance] Fast-forwarding dealing (all-in)")
            return _fast_forward_dealing(current_state, deck, events)

        # Normal progression: deal next street or go to showdown
        next_street = _get_next_street(current_state.street)
        print(f"[AutoAdvance] Betting round complete, advancing from {current_state.street.value} to {next_street.value}")
        
        if next_street == Street.SHOWDOWN:
            # Go to showdown
            print(f"[AutoAdvance] Going to showdown")
            return _resolve_showdown(current_state, events)
        else:
            # Deal next street
            if deck is None:
                print(f"[AutoAdvance] ERROR: Cannot advance to {next_street.value} - deck is None!")
                return current_state, events
            print(f"[AutoAdvance] Dealing {next_street.value}")
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
    from engine.rules.legality import next_player_to_act

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

    # Set to_act_seat to the first player to act on the new street
    # On postflop streets (FLOP, TURN, RIVER), the small blind acts first (or first active player after button)
    # In heads-up (2 players), the button acts first postflop
    active_seats = [
        i for i, player in enumerate(current_state.seats)
        if player is not None and player.status in (PlayerStatus.ACTIVE, PlayerStatus.ALL_IN)
    ]
    
    if len(active_seats) == 2 and current_state.button_seat is not None:
        # Heads-up: button acts first postflop
        to_act_seat = current_state.button_seat if current_state.button_seat in active_seats else active_seats[0]
    elif current_state.sb_seat is not None and current_state.sb_seat in active_seats:
        # Multi-way: small blind acts first postflop
        to_act_seat = current_state.sb_seat
    else:
        # Fallback: first active player after button
        if current_state.button_seat is not None:
            button_idx = active_seats.index(current_state.button_seat) if current_state.button_seat in active_seats else -1
            to_act_seat = active_seats[(button_idx + 1) % len(active_seats)] if active_seats else None
        else:
            to_act_seat = active_seats[0] if active_seats else None
    
    if to_act_seat is not None:
        current_state = current_state.model_copy(update={"to_act_seat": to_act_seat})
        print(f"[AutoAdvance] Set to_act_seat to {to_act_seat} after dealing {next_street.value}")
    else:
        # Use next_player_to_act as fallback
        next_seat = next_player_to_act(current_state.model_copy(update={"to_act_seat": active_seats[0] if active_seats else None}))
        if next_seat is not None:
            current_state = current_state.model_copy(update={"to_act_seat": next_seat})
            print(f"[AutoAdvance] Set to_act_seat to {next_seat} using next_player_to_act after dealing {next_street.value}")

    return current_state, current_events


def _resolve_showdown(
    state: GameState, events: list[DomainEvent]
) -> tuple[GameState, list[DomainEvent]]:
    """Resolve showdown by evaluating hands and splitting pots."""
    from engine.domain.events import ShowdownResolved
    from engine.eval.evaluator import evaluate_hand, HandValue
    from engine.reducer.reducer import apply_event

    current_state = state
    current_events = list(events)

    # Build side pots
    pots = build_side_pots(current_state)
    if not pots:
        print("[AutoAdvance] No pots to distribute in showdown")
        winners = {}
    else:
        # Get active players with their hole cards
        active_players = {}
        player_hands = {}
        for seat_id, player in enumerate(current_state.seats):
            if player is not None and player.status != PlayerStatus.FOLDED:
                if player.hole_cards and len(current_state.community_cards) >= 5:
                    # Evaluate hand
                    hand_value = evaluate_hand(player.hole_cards, list(current_state.community_cards))
                    active_players[seat_id] = player
                    player_hands[seat_id] = hand_value
                    print(f"[AutoAdvance] Seat {seat_id} hand: rank={hand_value.rank}, kickers={hand_value.kickers}")
                elif player.hole_cards:
                    # Not enough community cards - this shouldn't happen at showdown
                    print(f"[AutoAdvance] Warning: Seat {seat_id} has hole cards but only {len(current_state.community_cards)} community cards")
                else:
                    # No hole cards - shouldn't happen, but handle gracefully
                    print(f"[AutoAdvance] Warning: Seat {seat_id} is active but has no hole cards")

        if not active_players:
            print("[AutoAdvance] No active players for showdown")
            winners = {}
        else:
            # Distribute each pot to the best eligible hand(s)
            winners = {}
            for pot in pots:
                # Find best hand among eligible players
                eligible_hands = {
                    seat_id: hand_value
                    for seat_id, hand_value in player_hands.items()
                    if seat_id in pot.eligible_seats
                }
                
                if not eligible_hands:
                    print(f"[AutoAdvance] No eligible players for pot of {pot.amount}")
                    continue
                
                # Find best hand value
                best_hand: HandValue | None = None
                best_seats = []
                for seat_id, hand_value in eligible_hands.items():
                    if best_hand is None or hand_value > best_hand:
                        best_hand = hand_value
                        best_seats = [seat_id]
                    elif hand_value == best_hand:
                        best_seats.append(seat_id)
                
                # Split pot among winners (if multiple ties)
                amount_per_winner = pot.amount // len(best_seats)
                remainder = pot.amount % len(best_seats)
                
                for i, seat_id in enumerate(best_seats):
                    amount = amount_per_winner
                    if i < remainder:
                        amount += 1
                    winners[seat_id] = winners.get(seat_id, 0) + amount
                    print(f"[AutoAdvance] Pot of {pot.amount} split: Seat {seat_id} wins {amount} (best hand among eligible)")

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
