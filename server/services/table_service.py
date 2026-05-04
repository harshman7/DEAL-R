"""Table service: orchestrates command processing, event persistence, and broadcasting."""

import json

from engine.domain.commands import Command, StartHand
from engine.domain.events import DomainEvent
from engine.domain.state import GameState
from engine.domain.types import Deck
from engine.reducer.reducer import apply_event, next_state
from server.persistence.event_store import EventStore


class TableService:
    """Service for managing table state and processing commands."""

    def __init__(self, event_store: EventStore, table_id: str = "default"):
        """Initialize table service.

        Args:
            event_store: Event store instance
            table_id: Table identifier
        """
        self.event_store = event_store
        self.table_id = table_id
        self.current_state: GameState | None = None
        self.hand_id: str | None = None
        self._cleared_on_startup = False  # Track if we've cleared players on startup

    def get_state(self) -> GameState:
        """Get current table state.

        SIMPLE: Use cached state if available, only reload when necessary.
        On first load, clears all seated players (server restart cleanup).
        """
        # SIMPLE: Return cached state if we have it
        if self.current_state is not None:
            return self.current_state

        # Only reload if we don't have cached state
        # Load pre-hand events (table-level stream) first
        table_stream_id = f"table-{self.table_id}"
        table_events = self.event_store.get_events(table_stream_id)

        # If we have a hand, also load hand events
        if self.hand_id:
            hand_events = self.event_store.get_events(self.hand_id)
            if hand_events:
                # Combine table events (SitDown, etc.) with hand events
                all_events = (table_events or []) + hand_events
                self.current_state = self._replay_events(all_events)
        else:
            # No hand yet - just replay table events
            if table_events:
                self.current_state = self._replay_events(table_events)
            else:
                # No events yet - create fresh state (max 6 players per table)
                self.current_state = GameState(num_seats=6)

        # SIMPLE: On first load, clear all seated players (server restart cleanup)
        if not self._cleared_on_startup and self.current_state is not None:
            self._clear_seated_players()
            self._cleared_on_startup = True

        assert self.current_state is not None
        return self.current_state

    def _clear_seated_players(self):
        """Clear all seated players (called on server startup).

        When server restarts, WebSocket connections are lost but events persist.
        This clears all seated players so they need to rejoin.
        """
        import time

        from engine.domain.events import PlayerStoodUp

        # Find all seated players
        seated_players = []
        for seat in self.current_state.seats:
            if seat is not None:
                seated_players.append(seat.seat_id)

        if not seated_players:
            return  # No players to clear

        # Add PlayerStoodUp events for each seated player
        table_stream_id = f"table-{self.table_id}"
        current_version = self.event_store.get_current_version(table_stream_id)

        stand_up_events = []
        for seat_id in seated_players:
            event = PlayerStoodUp(timestamp=time.time(), seat_id=seat_id)
            stand_up_events.append(event)

        if stand_up_events:
            # Append events to clear players
            try:
                self.event_store.append_events(table_stream_id, current_version, stand_up_events)
                # Replay events to update state
                table_events = self.event_store.get_events(table_stream_id)
                if self.hand_id:
                    hand_events = self.event_store.get_events(self.hand_id)
                    all_events = (table_events or []) + (hand_events or [])
                    self.current_state = self._replay_events(all_events)
                else:
                    self.current_state = self._replay_events(table_events)
                print(
                    f"[TableService] Cleared {len(seated_players)} seated players from table {self.table_id} on startup"
                )
            except Exception as e:
                print(f"[TableService] Warning: Could not clear seated players: {e}")
                # If clearing fails, just set seats to None directly
                updated_seats = [None] * len(self.current_state.seats)
                self.current_state = self.current_state.model_copy(update={"seats": updated_seats})

    def process_command(
        self, command: Command, idempotency_key: str, expected_version: int
    ) -> tuple[GameState, list[DomainEvent], int]:
        """Process a command with idempotency and optimistic concurrency.

        Args:
            command: Command to process
            idempotency_key: Unique command identifier
            expected_version: Expected current version

        Returns:
            Tuple of (new_state, events, new_version)

        Raises:
            ValueError: If command is duplicate or version mismatch
        """
        # Check idempotency
        existing_result = self.event_store.get_command_result(idempotency_key)
        if existing_result:
            # Command already processed - return cached result
            # Reload state from events to ensure consistency
            state = self.get_state()
            event_stream_id = self.hand_id or f"table-{self.table_id}"
            version = self.event_store.get_current_version(event_stream_id)
            return state, [], version

        # Get current state (always fresh from events)
        state = self.get_state()

        # Get current version for optimistic concurrency
        event_stream_id = self.hand_id or f"table-{self.table_id}"
        current_version = self.event_store.get_current_version(event_stream_id)

        # If expected_version is 0 and we have events, use current version
        if expected_version == 0 and current_version > 0:
            expected_version = current_version

        # Create deck for commands that need it (StartHand, Act for auto-advance)
        import hashlib

        deck = None
        if isinstance(command, StartHand):
            # Create deck from seed_commit (hash to int) - SIMPLE approach
            seed_int = int(hashlib.sha256(command.seed_commit.encode()).hexdigest(), 16) % (2**31)
            deck = Deck.create_shuffled(seed_int)
            print(f"[TableService] Created deck for hand {command.hand_id} with seed {seed_int}")
        elif self.hand_id and state.seed_commit:
            # For Act commands (and others) after hand starts, recreate deck from seed_commit
            # This allows auto-advance to work correctly (it needs deck to deal next street)
            # Use seed_reveal if available, otherwise use seed_commit
            if state.seed_reveal:
                seed_int = state.seed_reveal
                print(f"[TableService] Using seed_reveal for deck: {seed_int}")
            else:
                # Recreate same seed from seed_commit (deterministic)
                seed_int = int(hashlib.sha256(state.seed_commit.encode()).hexdigest(), 16) % (2**31)
                print(
                    f"[TableService] Recreating deck from seed_commit for hand {self.hand_id}: seed={seed_int}, street={state.street.value}"
                )
            deck = Deck.create_shuffled(seed_int)
            print(
                f"[TableService] ✓ Deck ready for auto-advance (deck size check: {len(deck.cards) if hasattr(deck, 'cards') else 'N/A'})"
            )

        # Process command
        new_state, events = next_state(state, command, deck=deck)

        # Append events with optimistic concurrency
        if self.hand_id:
            # Hand has started - use hand_id
            new_version = self.event_store.append_events(event_stream_id, expected_version, events)
        else:
            # Before hand starts - use table-level stream
            if isinstance(command, StartHand):
                self.hand_id = command.hand_id
                # Start new hand stream
                new_version = self.event_store.append_events(self.hand_id, 0, events)
            else:
                # Store pre-hand events (like SitDown) in table stream
                new_version = self.event_store.append_events(
                    event_stream_id, expected_version, events
                )

        # Record command for idempotency
        command_data = json.dumps({"type": type(command).__name__, "data": command.__dict__})
        # Use event_store's serialization method to ensure consistency
        events_json = json.dumps([self.event_store._serialize_event(e) for e in events])
        event_stream_id = self.hand_id or f"table-{self.table_id}"
        self.event_store.record_command(
            idempotency_key, event_stream_id, type(command).__name__, command_data
        )
        self._update_command_result(idempotency_key, events_json)

        # SIMPLE: Update cached state directly (no reload needed)
        self.current_state = new_state

        return new_state, events, new_version

    def _replay_events(self, events: list[DomainEvent]) -> GameState:
        """Replay events to reconstruct state, re-dealing cards deterministically."""
        import hashlib

        from engine.domain.events import HandStarted

        state = GameState(num_seats=6)
        deck = None  # Will be created when HandStarted event is encountered

        for event in events:
            state = apply_event(state, event)

            # Re-deal cards deterministically when HandStarted event is encountered
            if isinstance(event, HandStarted) and event.seed_commit:
                # Create deck from seed_commit (same logic as process_command)
                seed_int = int(hashlib.sha256(event.seed_commit.encode()).hexdigest(), 16) % (2**31)
                deck = Deck.create_shuffled(seed_int)
                print(
                    f"[TableService] Replaying: Created deck from seed_commit for hand {event.hand_id} with seed {seed_int}"
                )

                # Re-deal cards to all seated players (they should be ACTIVE after HandStarted)
                # Use the same logic as _handle_start_hand: get all active seats
                active_seats = [i for i, player in enumerate(state.seats) if player is not None]

                if not active_seats:
                    print("[TableService] Replaying: No active players found for re-dealing cards")
                    continue

                updated_seats = list(state.seats)
                for seat_id in active_seats:
                    if seat_id >= len(updated_seats):
                        continue
                    seated = updated_seats[seat_id]
                    if seated is None:
                        continue
                    hole_cards = deck.deal(2)
                    updated_seats[seat_id] = seated.model_copy(
                        update={"hole_cards": tuple(hole_cards)}
                    )
                    print(
                        f"[TableService] Replaying: Re-dealt cards to seat {seat_id} (player_id={seated.player_id}): {hole_cards[0]}, {hole_cards[1]}"
                    )

                state = state.model_copy(update={"seats": updated_seats})
                print(f"[TableService] Replaying: Re-dealt cards to {len(active_seats)} players")

        return state

    def _update_command_result(self, idempotency_key: str, events_json: str) -> None:
        """Update command with result events."""
        self.event_store.update_command_result(idempotency_key, events_json)

    def load_hand(self, hand_id: str) -> GameState:
        """Load a hand by replaying events."""
        events = self.event_store.get_events(hand_id)
        state = self._replay_events(events)
        self.hand_id = hand_id
        self.current_state = state
        return state
