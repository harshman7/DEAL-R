"""Tests for domain types: Card, Deck, Money, SeatId."""

import pytest

from engine.domain.types import Card, Deck, Rank, Suit


class TestCard:
    """Test Card representation."""

    def test_card_creation(self):
        """Test creating cards."""
        card = Card(rank=Rank.ACE, suit=Suit.SPADES)
        assert card.rank == Rank.ACE
        assert card.suit == Suit.SPADES

    def test_card_equality(self):
        """Test card equality."""
        card1 = Card(rank=Rank.KING, suit=Suit.HEARTS)
        card2 = Card(rank=Rank.KING, suit=Suit.HEARTS)
        card3 = Card(rank=Rank.KING, suit=Suit.DIAMONDS)
        assert card1 == card2
        assert card1 != card3

    def test_card_string_representation(self):
        """Test card string formatting."""
        card = Card(rank=Rank.ACE, suit=Suit.SPADES)
        assert "A" in str(card)
        assert "♠" in str(card)


class TestDeck:
    """Test Deck creation and dealing."""

    def test_deck_creation(self):
        """Test creating a full deck."""
        deck = Deck()
        assert len(deck.cards) == 52
        assert deck.cursor == 0
        assert deck.remaining() == 52

    def test_deck_has_all_cards(self):
        """Test deck contains all 52 unique cards."""
        deck = Deck()
        seen = set()
        for card in deck.cards:
            assert card not in seen, f"Duplicate card: {card}"
            seen.add(card)
        assert len(seen) == 52

    def test_deck_deal(self):
        """Test dealing cards."""
        deck = Deck()
        cards = deck.deal(5)
        assert len(cards) == 5
        assert deck.cursor == 5
        assert deck.remaining() == 47

    def test_deck_deal_multiple(self):
        """Test dealing multiple times."""
        deck = Deck()
        cards1 = deck.deal(2)
        cards2 = deck.deal(3)
        assert len(cards1) == 2
        assert len(cards2) == 3
        assert deck.cursor == 5
        # Cards should be different
        assert set(cards1).isdisjoint(set(cards2))

    def test_deck_deal_insufficient_cards(self):
        """Test dealing more cards than available raises error."""
        deck = Deck()
        deck.deal(50)
        with pytest.raises(ValueError, match="Cannot deal"):
            deck.deal(5)

    def test_deck_reset(self):
        """Test resetting deck cursor."""
        deck = Deck()
        deck.deal(10)
        assert deck.cursor == 10
        deck.reset()
        assert deck.cursor == 0
        assert deck.remaining() == 52

    def test_deck_deterministic_shuffle(self):
        """Test that same seed produces same shuffle order."""
        seed = 42
        deck1 = Deck.create_shuffled(seed)
        deck2 = Deck.create_shuffled(seed)

        # Same seed should produce same order
        assert deck1.cards == deck2.cards
        assert deck1.get_seed() == seed
        assert deck2.get_seed() == seed

    def test_deck_different_seeds_different_order(self):
        """Test that different seeds produce different orders."""
        deck1 = Deck.create_shuffled(42)
        deck2 = Deck.create_shuffled(43)

        # Different seeds should (almost certainly) produce different orders
        assert deck1.cards != deck2.cards

    def test_deck_deterministic_dealing(self):
        """Test that dealing from same seed produces same cards."""
        seed = 12345
        deck1 = Deck.create_shuffled(seed)
        deck2 = Deck.create_shuffled(seed)

        cards1 = deck1.deal(5)
        cards2 = deck2.deal(5)

        assert cards1 == cards2

    def test_deck_serialization_compatible(self):
        """Test that deck state can be reconstructed for replay."""
        seed = 999
        deck = Deck.create_shuffled(seed)
        initial_cursor = deck.cursor

        # Deal some cards
        dealt1 = deck.deal(2)
        cursor_after = deck.cursor

        # Reset and recreate from same seed
        deck2 = Deck.create_shuffled(seed)
        assert deck2.cursor == initial_cursor
        dealt2 = deck2.deal(2)

        # Should get same cards
        assert dealt1 == dealt2
        assert deck2.cursor == cursor_after
