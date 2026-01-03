"""Domain events emitted by the reducer.

Events represent things that have happened in the game. State is derived
by applying events in order. Events are immutable and serializable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from engine.domain.state import PlayerStatus, Street
from engine.domain.types import Card, Money, SeatId


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events.

    Events are immutable and represent facts that have occurred.
    """

    timestamp: float  # Unix timestamp when event occurred


@dataclass(frozen=True)
class PlayerSatDown(DomainEvent):
    """Event: Player sat down at a seat."""

    seat_id: SeatId
    player_id: str
    stack: Money


@dataclass(frozen=True)
class PlayerStoodUp(DomainEvent):
    """Event: Player left their seat."""

    seat_id: SeatId


@dataclass(frozen=True)
class HandStarted(DomainEvent):
    """Event: A new hand has started.

    Args:
        hand_id: Unique hand identifier
        button_seat: Dealer button seat
        sb_seat: Small blind seat
        bb_seat: Big blind seat
        seed_commit: Committed seed hash
    """

    hand_id: str
    button_seat: SeatId
    sb_seat: SeatId
    bb_seat: SeatId
    seed_commit: str


@dataclass(frozen=True)
class SeedRevealed(DomainEvent):
    """Event: RNG seed has been revealed."""

    seed_reveal: int


@dataclass(frozen=True)
class CardsDealt(DomainEvent):
    """Event: Cards were dealt to a player.

    Args:
        seat_id: Seat receiving cards
        cards: Tuple of (card1, card2) - server-only, not in serialized event
    """

    seat_id: SeatId
    # Note: cards are server-only and excluded from serialization
    # They're included here for reducer logic but won't be persisted


@dataclass(frozen=True)
class BlindPosted(DomainEvent):
    """Event: A blind was posted.

    Args:
        seat_id: Seat posting the blind
        amount: Blind amount
        blind_type: "SB" or "BB"
    """

    seat_id: SeatId
    amount: Money
    blind_type: str  # "SB" or "BB"


@dataclass(frozen=True)
class ActionApplied(DomainEvent):
    """Event: A player action was applied.

    Args:
        seat_id: Seat that acted
        action_type: FOLD, CHECK, CALL, BET, or RAISE
        amount: Amount bet/raised (None for FOLD/CHECK)
        chips_committed: Total chips committed by this action
        new_stack: Player's stack after action
    """

    seat_id: SeatId
    action_type: str  # "FOLD", "CHECK", "CALL", "BET", "RAISE"
    amount: Optional[Money]
    chips_committed: Money
    new_stack: Money


@dataclass(frozen=True)
class StreetDealt(DomainEvent):
    """Event: A new betting street was dealt (flop, turn, river).

    Args:
        street: The new street (FLOP, TURN, RIVER)
        cards: Community cards dealt (3 for flop, 1 for turn/river)
    """

    street: Street
    cards: tuple[Card, ...]


@dataclass(frozen=True)
class BettingRoundComplete(DomainEvent):
    """Event: A betting round has completed.

    All active players have acted and betting is closed.
    """

    street: Street


@dataclass(frozen=True)
class PotCreated(DomainEvent):
    """Event: A pot (main or side pot) was created.

    Args:
        pot_index: Index of pot (0 = main pot)
        amount: Pot amount
        eligible_seats: Set of seat IDs eligible for this pot
    """

    pot_index: int
    amount: Money
    eligible_seats: frozenset[SeatId]


@dataclass(frozen=True)
class ShowdownResolved(DomainEvent):
    """Event: Showdown completed and pots awarded.

    Args:
        winners: Dict mapping seat_id -> amount won
    """

    winners: dict[SeatId, Money]


@dataclass(frozen=True)
class HandEnded(DomainEvent):
    """Event: Hand has ended.

    Args:
        winner_seat: Seat that won (if single winner, None if split)
        reason: "SHOWDOWN", "FOLD", etc.
    """

    winner_seat: Optional[SeatId]
    reason: str

