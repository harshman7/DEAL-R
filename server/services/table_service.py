"""Table service: orchestrates command processing, event persistence, and broadcasting."""

import json
from typing import Optional

from engine.domain.commands import Act, ActionType, Command, SitDown, StartHand
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
        self.current_state: Optional[GameState] = None
        self.hand_id: Optional[str] = None

    def get_state(self) -> GameState:
        """Get current table state.
        
        Always reloads from events to ensure consistency across connections.
        After reloading, re-deals cards deterministically if we have a seed.
        """
        # Always reload from events to ensure consistency across connections
        # Load pre-hand events (table-level stream) first
        table_stream_id = f"table-{self.table_id}"
        table_events = self.event_store.get_events(table_stream_id)
        
        # If we have a hand, also load hand events
        if self.hand_id:
            hand_events = self.event_store.get_events(self.hand_id)
            if hand_events:
                # Combine table events (SitDown, etc.) with hand events
                all_events = (table_events or []) + hand_events
                state = self._replay_events(all_events)
                # Re-deal cards deterministically if we have a seed
                state = self._redeal_cards(state, hand_events)
                self.current_state = state
                return self.current_state
        
        # No hand yet - just replay table events
        if table_events:
            # Replay table events to get current state
            self.current_state = self._replay_events(table_events)
            return self.current_state
        else:
            # No events yet - create fresh state
            if self.current_state is None:
                self.current_state = GameState(num_seats=9)
        
        return self.current_state
    
    def _redeal_cards(self, state: GameState, events: list[DomainEvent]) -> GameState:
        """Re-deal cards deterministically after replaying events.
        
        Since hole_cards aren't stored in events (for security), we need to
        re-deal them deterministically from the seed when reloading state.
        """
        from engine.domain.events import HandStarted, CardsDealt
        
        # Find HandStarted event to get seed_commit
        hand_started = None
        for event in events:
            if isinstance(event, HandStarted):
                hand_started = event
                break
        
        if not hand_started or not hand_started.seed_commit:
            return state
        
        # Find all CardsDealt events to know which seats got cards
        cards_dealt_seats = []
        for event in events:
            if isinstance(event, CardsDealt):
                cards_dealt_seats.append(event.seat_id)
        
        if not cards_dealt_seats:
            return state
        
        # Create deck from seed_commit (same logic as StartHand processing)
        import hashlib
        seed_int = int(hashlib.sha256(hand_started.seed_commit.encode()).hexdigest(), 16) % (2**31)
        deck = Deck.create_shuffled(seed_int)
        
        # Re-deal cards to the same seats in the same order
        updated_seats = list(state.seats)
        for seat_id in cards_dealt_seats:
            if seat_id < len(updated_seats) and updated_seats[seat_id] is not None:
                hole_cards = deck.deal(2)
                player = updated_seats[seat_id]
                updated_seats[seat_id] = player.model_copy(update={"hole_cards": tuple(hole_cards)})
        
        return state.model_copy(update={"seats": updated_seats})

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

        # SIMPLE: Create deck for StartHand command
        deck = None
        if isinstance(command, StartHand):
            # Create deck from seed_commit (hash to int) - SIMPLE approach
            import hashlib
            seed_int = int(hashlib.sha256(command.seed_commit.encode()).hexdigest(), 16) % (2**31)
            deck = Deck.create_shuffled(seed_int)
            print(f"[TableService] Created deck for hand {command.hand_id} with seed {seed_int}")
        elif self.hand_id and state.seed_reveal:
            # For other commands after seed reveal, use seed_reveal
            deck = Deck.create_shuffled(state.seed_reveal)

        # Process command
        new_state, events = next_state(state, command, deck=deck)

        # Append events with optimistic concurrency
        if self.hand_id:
            # Hand has started - use hand_id
            new_version = self.event_store.append_events(
                event_stream_id, expected_version, events
            )
        else:
            # Before hand starts - use table-level stream
            if isinstance(command, StartHand):
                self.hand_id = command.hand_id
                # Start new hand stream
                new_version = self.event_store.append_events(
                    self.hand_id, 0, events
                )
            else:
                # Store pre-hand events (like SitDown) in table stream
                # This allows multiple connections to see the same state
                new_version = self.event_store.append_events(
                    event_stream_id, expected_version, events
                )

        # Record command for idempotency (store result events)
        command_data = json.dumps({"type": type(command).__name__, "data": command.__dict__})
        events_json = json.dumps([self._serialize_event(e) for e in events])
        event_stream_id = self.hand_id or f"table-{self.table_id}"
        self.event_store.record_command(
            idempotency_key, event_stream_id, type(command).__name__, command_data
        )
        # Update command with result events
        self._update_command_result(idempotency_key, events_json)

        # Don't cache state - always reload from events for consistency
        # This ensures all connections see the same state
        self.current_state = None  # Force reload on next get_state()

        return new_state, events, new_version

    def _replay_events(self, events: list[DomainEvent]) -> GameState:
        """Replay events to reconstruct state."""
        state = GameState(num_seats=9)
        for event in events:
            state = apply_event(state, event)
        return state

    def _serialize_event(self, event: DomainEvent) -> str:
        """Serialize event to JSON string."""
        return json.dumps({"type": type(event).__name__, "data": event.__dict__})

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

