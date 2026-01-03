"""Command types for poker game actions.

Commands represent user intentions. They are validated and processed by the reducer,
which emits events. Commands are idempotent - the same command with the same
idempotency_key should produce the same events.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from engine.domain.types import Money, SeatId


class ActionType(str, Enum):
    """Player action types."""

    FOLD = "FOLD"
    CHECK = "CHECK"
    CALL = "CALL"
    BET = "BET"
    RAISE = "RAISE"


@dataclass(frozen=True)
class Command:
    """Base command class.

    All commands have an idempotency_key to prevent duplicate processing.
    """

    idempotency_key: str
    timestamp: float  # Unix timestamp


@dataclass(frozen=True)
class SitDown(Command):
    """Command to seat a player at the table.

    Args:
        seat_id: Seat to sit at (0-based)
        stack: Starting chip stack
        player_id: Unique player identifier
    """

    seat_id: SeatId
    stack: Money
    player_id: str


@dataclass(frozen=True)
class StandUp(Command):
    """Command to remove a player from the table.

    Args:
        seat_id: Seat to vacate
    """

    seat_id: SeatId


@dataclass(frozen=True)
class StartHand(Command):
    """Command to start a new hand.

    Args:
        hand_id: Unique hand identifier
        seed_commit: Committed seed hash (before reveal)
    """

    hand_id: str
    seed_commit: str


@dataclass(frozen=True)
class RevealSeed(Command):
    """Command to reveal the RNG seed after commit phase.

    Args:
        seed_reveal: The actual seed value
    """

    seed_reveal: int


@dataclass(frozen=True)
class Act(Command):
    """Command for a player action (fold, check, call, bet, raise).

    Args:
        seat_id: Seat making the action
        action_type: Type of action (FOLD, CHECK, CALL, BET, RAISE)
        amount: Bet/raise amount (required for BET/RAISE, ignored for others)
    """

    seat_id: SeatId
    action_type: ActionType
    amount: Optional[Money] = None  # Required for BET/RAISE

