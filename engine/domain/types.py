"""Shared domain types: Card, Deck, Money, SeatId."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class Rank(IntEnum):
    """Card rank (2-14, where 14 is Ace)."""

    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14


class Suit(IntEnum):
    """Card suit."""

    CLUBS = 0
    DIAMONDS = 1
    HEARTS = 2
    SPADES = 3


@dataclass(frozen=True, order=True)
class Card:
    """Immutable card representation."""

    rank: Rank
    suit: Suit

    def __str__(self) -> str:
        """Human-readable card representation."""
        rank_str = {
            Rank.ACE: "A",
            Rank.KING: "K",
            Rank.QUEEN: "Q",
            Rank.JACK: "J",
        }.get(self.rank, str(self.rank.value))
        suit_str = {
            Suit.CLUBS: "♣",
            Suit.DIAMONDS: "♦",
            Suit.HEARTS: "♥",
            Suit.SPADES: "♠",
        }[self.suit]
        return f"{rank_str}{suit_str}"

    def __repr__(self) -> str:
        """Developer representation."""
        return f"Card(rank={self.rank.name}, suit={self.suit.name})"


# Type aliases
Money = int  # Chips in cents or smallest unit
SeatId = int  # Seat index (0-based)


@dataclass
class Deck:
    """Deterministic deck with cursor for dealing cards.

    The deck maintains a cursor position and uses a seeded RNG for shuffling.
    Given the same seed, the shuffle order is deterministic.
    """

    cards: list[Card] = field(default_factory=list)
    cursor: int = 0
    _seed: Optional[int] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize a full 52-card deck if not provided."""
        if not self.cards:
            self.cards = [
                Card(rank=rank, suit=suit)
                for suit in Suit
                for rank in Rank
            ]

    @classmethod
    def create_shuffled(cls, seed: int) -> Deck:
        """Create a shuffled deck using the given seed.

        Args:
            seed: Random seed for deterministic shuffling

        Returns:
            A new shuffled Deck instance
        """
        deck = cls()
        rng = random.Random(seed)
        rng.shuffle(deck.cards)
        deck._seed = seed
        return deck

    def deal(self, count: int = 1) -> list[Card]:
        """Deal cards from the current cursor position.

        Args:
            count: Number of cards to deal

        Returns:
            List of dealt cards

        Raises:
            ValueError: If insufficient cards remain
        """
        if self.cursor + count > len(self.cards):
            raise ValueError(
                f"Cannot deal {count} cards: only {len(self.cards) - self.cursor} remaining"
            )
        dealt = self.cards[self.cursor : self.cursor + count]
        self.cursor += count
        return dealt

    def remaining(self) -> int:
        """Return number of cards remaining to be dealt."""
        return len(self.cards) - self.cursor

    def reset(self) -> None:
        """Reset cursor to beginning (for replay/testing)."""
        self.cursor = 0

    def get_seed(self) -> Optional[int]:
        """Get the seed used for shuffling (if any)."""
        return self._seed

