"""Demonstration of deterministic deck shuffling and dealing."""

from engine.domain.types import Deck

if __name__ == "__main__":
    print("=== Deterministic Deck Demo ===\n")

    seed = 42

    # Create two decks with the same seed
    print(f"Creating two decks with seed={seed}...")
    deck1 = Deck.create_shuffled(seed)
    deck2 = Deck.create_shuffled(seed)

    # Verify they have the same order
    print(f"Decks have same order: {deck1.cards == deck2.cards}")
    print(f"First 5 cards from deck1: {[str(c) for c in deck1.cards[:5]]}")
    print(f"First 5 cards from deck2: {[str(c) for c in deck2.cards[:5]]}\n")

    # Deal cards and verify determinism
    print("Dealing 5 cards from each deck...")
    hand1 = deck1.deal(5)
    hand2 = deck2.deal(5)

    print(f"Hand 1: {[str(c) for c in hand1]}")
    print(f"Hand 2: {[str(c) for c in hand2]}")
    print(f"Hands are identical: {hand1 == hand2}\n")

    # Deal more cards
    print("Dealing 3 more cards...")
    flop1 = deck1.deal(3)
    flop2 = deck2.deal(3)

    print(f"Flop 1: {[str(c) for c in flop1]}")
    print(f"Flop 2: {[str(c) for c in flop2]}")
    print(f"Flops are identical: {flop1 == flop2}\n")

    print("✅ Determinism verified: Same seed produces identical results!")

