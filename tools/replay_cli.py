#!/usr/bin/env python3
"""CLI tool to replay events from database and verify determinism.

Usage:
    python -m tools.replay_cli <hand_id> [--db-url DATABASE_URL]
"""

import argparse
import hashlib
import json
import sys
from typing import Optional

from engine.domain.state import GameState
from engine.reducer.reducer import apply_event
from server.persistence.event_store import EventStore


def hash_state(state: GameState) -> str:
    """Compute deterministic hash of game state.

    Args:
        state: Game state to hash

    Returns:
        Hexadecimal hash string
    """
    # Serialize state to JSON (deterministic)
    state_dict = state.model_dump()
    # Sort keys for deterministic ordering
    state_json = json.dumps(state_dict, sort_keys=True, default=str)
    return hashlib.sha256(state_json.encode()).hexdigest()


def replay_hand(hand_id: str, db_url: str) -> tuple[GameState, str]:
    """Replay a hand from events and return final state + hash.

    Args:
        hand_id: Hand identifier
        db_url: Database URL

    Returns:
        Tuple of (final_state, state_hash)
    """
    event_store = EventStore(db_url)
    events = event_store.get_events(hand_id)

    # Replay events
    state = GameState(num_seats=9)
    for event in events:
        state = apply_event(state, event)

    state_hash = hash_state(state)
    return state, state_hash


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Replay hand events and verify determinism")
    parser.add_argument("hand_id", help="Hand identifier to replay")
    parser.add_argument(
        "--db-url",
        default="sqlite:///./poker.db",
        help="Database URL (default: sqlite:///./poker.db)",
    )
    parser.add_argument("--hash-only", action="store_true", help="Output only the state hash")

    args = parser.parse_args()

    try:
        state, state_hash = replay_hand(args.hand_id, args.db_url)

        if args.hash_only:
            print(state_hash)
        else:
            print(f"Hand ID: {args.hand_id}")
            print(f"Final Street: {state.street.value}")
            print(f"State Hash: {state_hash}")
            print(f"\nActive Players: {state.count_active_players()}")
            print(f"Total Pots: {len(state.pots)}")
            if state.pots:
                total_pot = sum(pot.amount for pot in state.pots)
                print(f"Total Pot Amount: {total_pot}")

            # Show player stacks
            print("\nPlayer Stacks:")
            for i, player in enumerate(state.seats):
                if player is not None:
                    print(f"  Seat {i}: {player.stack} chips (status: {player.status.value})")

            print(f"\n✅ Replay successful - State hash: {state_hash}")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

