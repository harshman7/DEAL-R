#!/usr/bin/env python3
"""Export hand history in human-readable format.

Usage:
    python -m tools.hh_export <hand_id> [--db-url DATABASE_URL] [--output FILE]
"""

import argparse
import sys
from datetime import datetime

from engine.domain.state import GameState
from engine.domain.types import Card
from engine.reducer.reducer import apply_event
from server.persistence.event_store import EventStore


def format_card(card: Card) -> str:
    """Format card for display."""
    rank_map = {
        2: "2",
        3: "3",
        4: "4",
        5: "5",
        6: "6",
        7: "7",
        8: "8",
        9: "9",
        10: "T",
        11: "J",
        12: "Q",
        13: "K",
        14: "A",
    }
    suit_map = {0: "c", 1: "d", 2: "h", 3: "s"}
    return f"{rank_map[card.rank.value]}{suit_map[card.suit.value]}"


def export_hand_history(hand_id: str, db_url: str, output_file: str | None = None):
    """Export hand history in human-readable format.

    Args:
        hand_id: Hand identifier
        db_url: Database URL
        output_file: Optional output file path (stdout if None)
    """
    event_store = EventStore(db_url)
    events = event_store.get_events(hand_id)

    if not events:
        print(f"No events found for hand {hand_id}", file=sys.stderr)
        sys.exit(1)

    # Replay to get state
    state = GameState(num_seats=9)
    for event in events:
        state = apply_event(state, event)

    output = sys.stdout if output_file is None else open(output_file, "w")

    try:
        # Header
        output.write(f"Hand #{hand_id}\n")
        output.write(f"Date: {datetime.fromtimestamp(events[0].timestamp).isoformat()}\n")
        output.write(f"Table: {state.num_seats}-max\n")
        output.write(f"Blinds: {state.small_blind}/{state.big_blind}\n")
        output.write("\n")

        # Replay events and format
        current_state = GameState(num_seats=9)
        for i, event in enumerate(events):
            event_type = type(event).__name__

            if event_type == "HandStarted":
                output.write("*** HAND STARTED ***\n")
                output.write(f"Button: Seat {event.button_seat}\n")
                output.write(f"Small Blind: Seat {event.sb_seat}\n")
                output.write(f"Big Blind: Seat {event.bb_seat}\n")
                output.write("\n")

            elif event_type == "PlayerSatDown":
                output.write(
                    f"Seat {event.seat_id}: {event.player_id} sits down with {event.stack} chips\n"
                )

            elif event_type == "BlindPosted":
                output.write(f"Seat {event.seat_id}: posts {event.blind_type} {event.amount}\n")

            elif event_type == "ActionApplied":
                action_desc = event.action_type
                if event.amount:
                    action_desc += f" {event.amount}"
                output.write(f"Seat {event.seat_id}: {action_desc}\n")

            elif event_type == "StreetDealt":
                street_name = event.street.value
                if street_name == "FLOP":
                    cards_str = " ".join(format_card(c) for c in event.cards)
                    output.write(f"\n*** {street_name} *** [{cards_str}]\n")
                elif street_name in ("TURN", "RIVER"):
                    cards_str = format_card(event.cards[0]) if event.cards else ""
                    output.write(f"\n*** {street_name} *** [{cards_str}]\n")

            elif event_type == "ShowdownResolved":
                output.write("\n*** SHOWDOWN ***\n")
                for seat_id, amount in event.winners.items():
                    output.write(f"Seat {seat_id} wins {amount}\n")

            elif event_type == "HandEnded":
                output.write("\n*** HAND ENDED ***\n")
                output.write(f"Reason: {event.reason}\n")
                if event.winner_seat is not None:
                    output.write(f"Winner: Seat {event.winner_seat}\n")

            # Update state
            current_state = apply_event(current_state, event)

        # Final stacks
        output.write("\n*** FINAL STACKS ***\n")
        for i, player in enumerate(current_state.seats):
            if player is not None:
                output.write(f"Seat {i}: {player.stack} chips\n")

    finally:
        if output_file:
            output.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Export hand history in human-readable format")
    parser.add_argument("hand_id", help="Hand identifier to export")
    parser.add_argument(
        "--db-url",
        default="sqlite:///./poker.db",
        help="Database URL (default: sqlite:///./poker.db)",
    )
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    args = parser.parse_args()

    try:
        export_hand_history(args.hand_id, args.db_url, args.output)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
