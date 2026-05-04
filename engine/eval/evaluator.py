"""Hand evaluation and ranking for Texas Hold'em.

This module provides deterministic hand evaluation and ranking.
Hands are evaluated using standard poker hand rankings.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from engine.domain.types import Card


class HandRank:
    """Poker hand rankings (higher is better)."""

    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9
    ROYAL_FLUSH = 10


@dataclass(frozen=True, order=False)
class HandValue:
    """Represents a hand's value for comparison."""

    rank: int  # HandRank value
    kickers: tuple[int, ...]  # Kicker cards for tie-breaking (sorted descending)

    def __lt__(self, other: HandValue) -> bool:
        """Compare two hand values."""
        if self.rank != other.rank:
            return self.rank < other.rank
        return self.kickers < other.kickers

    def __eq__(self, other: object) -> bool:
        """Check if two hand values are equal."""
        if not isinstance(other, HandValue):
            return False
        return self.rank == other.rank and self.kickers == other.kickers


def evaluate_hand(hole_cards: tuple[Card, Card], board: list[Card]) -> HandValue:
    """Evaluate a 7-card hand (2 hole + 5 board).

    Args:
        hole_cards: Player's two hole cards
        board: Five community cards

    Returns:
        HandValue representing the best 5-card hand
    """
    all_cards = list(hole_cards) + board
    if len(all_cards) != 7:
        raise ValueError(f"Expected 7 cards, got {len(all_cards)}")

    # Try all possible 5-card combinations
    best_hand: HandValue | None = None
    for i in range(7):
        for j in range(i + 1, 7):
            five_cards = [all_cards[k] for k in range(7) if k != i and k != j]
            hand_value = _evaluate_five_cards(five_cards)
            if best_hand is None or hand_value > best_hand:
                best_hand = hand_value

    assert best_hand is not None  # Exhaustive iteration over combos
    return best_hand


def _evaluate_five_cards(cards: list[Card]) -> HandValue:
    """Evaluate a 5-card hand."""
    if len(cards) != 5:
        raise ValueError(f"Expected 5 cards, got {len(cards)}")

    ranks = [card.rank.value for card in cards]
    suits = [card.suit for card in cards]

    rank_counts = Counter(ranks)
    suit_counts = Counter(suits)

    # Check for flush
    is_flush = len(suit_counts) == 1

    # Check for straight
    sorted_ranks = sorted(set(ranks))
    is_straight = False
    if len(sorted_ranks) == 5:
        # Check normal straight
        if sorted_ranks[-1] - sorted_ranks[0] == 4:
            is_straight = True
        # Check A-2-3-4-5 straight (wheel)
        elif sorted_ranks == [2, 3, 4, 5, 14]:
            is_straight = True
            sorted_ranks = [1, 2, 3, 4, 5]  # Treat Ace as low

    # Check for straight flush / royal flush
    if is_straight and is_flush:
        if sorted_ranks == [10, 11, 12, 13, 14]:
            return HandValue(rank=HandRank.ROYAL_FLUSH, kickers=())
        return HandValue(rank=HandRank.STRAIGHT_FLUSH, kickers=(sorted_ranks[-1],))

    # Check for four of a kind
    if 4 in rank_counts.values():
        four_rank = next(rank for rank, count in rank_counts.items() if count == 4)
        kicker = next(rank for rank in ranks if rank != four_rank)
        return HandValue(rank=HandRank.FOUR_OF_A_KIND, kickers=(four_rank, kicker))

    # Check for full house
    if 3 in rank_counts.values() and 2 in rank_counts.values():
        three_rank = next(rank for rank, count in rank_counts.items() if count == 3)
        pair_rank = next(rank for rank, count in rank_counts.items() if count == 2)
        return HandValue(rank=HandRank.FULL_HOUSE, kickers=(three_rank, pair_rank))

    # Check for flush
    if is_flush:
        sorted_ranks_desc = sorted(ranks, reverse=True)
        return HandValue(rank=HandRank.FLUSH, kickers=tuple(sorted_ranks_desc))

    # Check for straight
    if is_straight:
        return HandValue(rank=HandRank.STRAIGHT, kickers=(sorted_ranks[-1],))

    # Check for three of a kind
    if 3 in rank_counts.values():
        three_rank = next(rank for rank, count in rank_counts.items() if count == 3)
        kickers = sorted([rank for rank in ranks if rank != three_rank], reverse=True)
        return HandValue(rank=HandRank.THREE_OF_A_KIND, kickers=(three_rank, *kickers))

    # Check for two pair
    pairs = [rank for rank, count in rank_counts.items() if count == 2]
    if len(pairs) == 2:
        pairs_sorted = sorted(pairs, reverse=True)
        kicker = next(rank for rank in ranks if rank not in pairs)
        return HandValue(rank=HandRank.TWO_PAIR, kickers=(*pairs_sorted, kicker))

    # Check for pair
    if 2 in rank_counts.values():
        pair_rank = next(rank for rank, count in rank_counts.items() if count == 2)
        kickers = sorted([rank for rank in ranks if rank != pair_rank], reverse=True)
        return HandValue(rank=HandRank.PAIR, kickers=(pair_rank, *kickers))

    # High card
    sorted_ranks_desc = sorted(ranks, reverse=True)
    return HandValue(rank=HandRank.HIGH_CARD, kickers=tuple(sorted_ranks_desc))


def rank_hands(players: dict[int, tuple[Card, Card]], board: list[Card]) -> dict[int, HandValue]:
    """Rank all players' hands.

    Args:
        players: Dict mapping seat_id -> (hole_card1, hole_card2)
        board: Community cards

    Returns:
        Dict mapping seat_id -> HandValue
    """
    rankings: dict[int, HandValue] = {}
    for seat_id, hole_cards in players.items():
        rankings[seat_id] = evaluate_hand(hole_cards, board)
    return rankings


def split_pot(pots: list, player_rankings: dict[int, HandValue]) -> dict[int, int]:
    """Split pots among winners.

    Args:
        pots: List of Pot objects
        player_rankings: Dict mapping seat_id -> HandValue

    Returns:
        Dict mapping seat_id -> amount won
    """
    winners: dict[int, int] = {}
    for pot in pots:
        # Find best hand among eligible players
        eligible_rankings = {
            seat_id: hand_value
            for seat_id, hand_value in player_rankings.items()
            if seat_id in pot.eligible_seats
        }

        if not eligible_rankings:
            continue

        # Find winner(s)
        best_hand = max(eligible_rankings.values())
        winning_seats = [
            seat_id for seat_id, hand_value in eligible_rankings.items() if hand_value == best_hand
        ]

        # Split pot evenly among winners
        amount_per_winner = pot.amount // len(winning_seats)
        remainder = pot.amount % len(winning_seats)

        for i, seat_id in enumerate(winning_seats):
            amount = amount_per_winner
            if i < remainder:  # Distribute remainder to first winners
                amount += 1
            winners[seat_id] = winners.get(seat_id, 0) + amount

    return winners
