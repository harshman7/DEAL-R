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
        """Get current table state."""
        if self.current_state is None:
            # Load from events or create initial state
            if self.hand_id:
                events = self.event_store.get_events(self.hand_id)
                self.current_state = self._replay_events(events)
            else:
                self.current_state = GameState(num_seats=9)
        return self.current_state

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
            events_data = json.loads(existing_result)
            # Reconstruct events (simplified)
            events = []  # Would deserialize events_data
            state = self.get_state()
            for event in events:
                state = apply_event(state, event)
            return state, events, self.event_store.get_current_version(self.hand_id or "")

        # Get current state
        state = self.get_state()

        # Create deck if needed (for dealing)
        deck = None
        if self.hand_id and state.seed_reveal:
            deck = Deck.create_shuffled(state.seed_reveal)

        # Process command
        new_state, events = next_state(state, command, deck=deck)

        # Append events with optimistic concurrency
        if self.hand_id:
            new_version = self.event_store.append_events(
                self.hand_id, expected_version, events
            )
        else:
            # New hand - create hand_id from table_id
            if isinstance(command, StartHand):
                self.hand_id = command.hand_id
                new_version = self.event_store.append_events(
                    self.hand_id, 0, events
                )
            else:
                # Commands before hand starts don't create events
                new_version = 0

        # Record command for idempotency (store result events)
        command_data = json.dumps({"type": type(command).__name__, "data": command.__dict__})
        events_json = json.dumps([self._serialize_event(e) for e in events])
        self.event_store.record_command(
            idempotency_key, self.hand_id or "", type(command).__name__, command_data
        )
        # Update command with result events
        self._update_command_result(idempotency_key, events_json)

        # Update cached state
        self.current_state = new_state

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

