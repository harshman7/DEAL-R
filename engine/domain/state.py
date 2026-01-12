"""Game state models: GameState, PlayerState, Pot."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field

from engine.domain.types import Card, Money, SeatId


class Street(str, Enum):
    """Betting street/round."""

    WAITING = "WAITING"  # Before hand starts
    PREFLOP = "PREFLOP"
    FLOP = "FLOP"
    TURN = "TURN"
    RIVER = "RIVER"
    SHOWDOWN = "SHOWDOWN"
    COMPLETE = "COMPLETE"


class PlayerStatus(str, Enum):
    """Player status in the current hand."""

    ACTIVE = "ACTIVE"  # Still in hand, can act
    FOLDED = "FOLDED"  # Folded this hand
    ALL_IN = "ALL_IN"  # All chips committed
    OUT = "OUT"  # Not in hand (sitting out or not seated)


@dataclass
class Pot:
    """Side pot with eligible players."""

    amount: Money
    eligible_seats: set[SeatId]

    def __repr__(self) -> str:
        """Developer representation."""
        return f"Pot(amount={self.amount}, seats={sorted(self.eligible_seats)})"


class PlayerState(BaseModel):
    """Player state at a table.

    Note: hole_cards is server-only and not included in serialized state
    for security (players shouldn't see others' cards).
    """

    seat_id: SeatId
    player_id: str | None = Field(default=None, description="Player identifier")
    stack: Money = Field(ge=0, description="Current chip stack")
    committed_street: Money = Field(
        default=0, ge=0, description="Chips committed this betting round"
    )
    committed_total: Money = Field(default=0, ge=0, description="Total chips committed this hand")
    status: PlayerStatus = PlayerStatus.OUT
    acted_this_street: bool = False
    hole_cards: tuple[Card, Card] | None = Field(
        default=None, exclude=True, description="Server-only: player's hole cards"
    )

    model_config = {
        "arbitrary_types_allowed": True,
    }

    def model_dump_public(self) -> dict:
        """Dump state without server-only fields (hole_cards)."""
        data = self.model_dump(exclude={"hole_cards"})
        return data


class GameState(BaseModel):
    """Complete game state for a poker table/hand.

    This is the single source of truth for game state. All state changes
    go through the reducer, which emits events. State is derived by
    applying events in order.
    """

    # Table configuration
    num_seats: int = Field(default=9, ge=2, le=10, description="Number of seats at table")
    small_blind: Money = Field(default=50, gt=0)
    big_blind: Money = Field(default=100, gt=0)

    # Seating
    seats: list[PlayerState | None] = Field(
        default_factory=list, description="Seat array (None = empty seat)"
    )

    # Hand state
    hand_id: str | None = Field(default=None, description="Unique hand identifier")
    street: Street = Street.WAITING
    button_seat: SeatId | None = Field(default=None, description="Dealer button seat")
    sb_seat: SeatId | None = Field(default=None, description="Small blind seat")
    bb_seat: SeatId | None = Field(default=None, description="Big blind seat")
    to_act_seat: SeatId | None = Field(default=None, description="Seat that must act next")

    # Community cards
    community_cards: list[Card] = Field(
        default_factory=list, description="Board cards (flop/turn/river)"
    )

    # Betting state
    current_bet: Money = Field(default=0, ge=0, description="Highest bet this street")
    min_raise: Money = Field(
        default=0, ge=0, description="Minimum raise amount (2x last raise or big blind)"
    )
    last_raiser_seat: SeatId | None = Field(default=None, description="Last seat that raised")

    # Pots
    pots: list[Pot] = Field(default_factory=list, description="Main pot + side pots")

    # RNG seed tracking (for deterministic replay)
    seed_commit: str | None = Field(default=None, description="Committed seed hash (before reveal)")
    seed_reveal: int | None = Field(default=None, description="Revealed seed (after commit phase)")

    # Hand results (stored after hand ends, cleared when new hand starts)
    last_hand_results: dict[SeatId, Money] | None = Field(
        default=None, description="Winners from last completed hand (seat_id -> amount won)"
    )

    model_config = {
        "arbitrary_types_allowed": True,
    }

    def __init__(self, **data):
        """Initialize with empty seats list."""
        if "seats" not in data:
            data["seats"] = [None] * data.get("num_seats", 9)
        super().__init__(**data)

    def get_active_players(self) -> list[PlayerState]:
        """Get all active (non-folded, non-out) players."""
        return [
            player
            for player in self.seats
            if player is not None and player.status in (PlayerStatus.ACTIVE, PlayerStatus.ALL_IN)
        ]

    def get_player(self, seat_id: SeatId) -> PlayerState | None:
        """Get player at seat, or None if empty."""
        if 0 <= seat_id < len(self.seats):
            return self.seats[seat_id]
        return None

    def count_active_players(self) -> int:
        """Count active players (not folded, not out)."""
        return len(self.get_active_players())
