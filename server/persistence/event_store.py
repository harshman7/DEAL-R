"""Event store with optimistic concurrency control."""

import json

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from engine.domain.events import DomainEvent
from server.config import settings
from server.persistence.models import Base, CommandModel, EventModel, HandSnapshotModel


class EventStore:
    """Event store with optimistic concurrency control."""

    def __init__(self, database_url: str):
        """Initialize event store.

        Args:
            database_url: SQLAlchemy database URL (e.g., postgresql://user:pass@localhost/db)
        """
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

    def append_events(self, hand_id: str, expected_version: int, events: list[DomainEvent]) -> int:
        """Append events with optimistic concurrency control.

        Args:
            hand_id: Hand identifier
            expected_version: Expected current version (for optimistic locking)
            events: List of events to append

        Returns:
            New version number after appending

        Raises:
            ValueError: If expected_version doesn't match current version
        """
        db: Session = self.SessionLocal()
        try:
            # Check current version
            current_version = self._get_current_version(db, hand_id)
            if current_version != expected_version:
                raise ValueError(
                    f"Version mismatch: expected {expected_version}, got {current_version}"
                )

            # Append events
            new_version = expected_version
            for event in events:
                new_version += 1
                event_model = EventModel(
                    hand_id=hand_id,
                    version=new_version,
                    event_type=type(event).__name__,
                    event_data=self._serialize_event(event),
                    timestamp=int(event.timestamp),
                )
                db.add(event_model)

            db.commit()

            # Create snapshot if interval reached
            if settings.snapshot_interval > 0 and new_version % settings.snapshot_interval == 0:
                # Note: State serialization should be done by caller
                # This is just a placeholder - actual snapshot creation happens in TableService
                pass

            return new_version

        except IntegrityError as e:
            db.rollback()
            raise ValueError(f"Concurrency conflict: {e}") from e
        finally:
            db.close()

    def get_events(self, hand_id: str, from_version: int = 0) -> list[DomainEvent]:
        """Get events for a hand.

        Args:
            hand_id: Hand identifier
            from_version: Starting version (inclusive)

        Returns:
            List of events in order
        """
        db: Session = self.SessionLocal()
        try:
            events = (
                db.query(EventModel)
                .filter(EventModel.hand_id == hand_id)
                .filter(EventModel.version >= from_version)
                .order_by(EventModel.version)
                .all()
            )
            return [self._deserialize_event(e) for e in events]
        finally:
            db.close()

    def get_events_with_snapshot(self, hand_id: str) -> tuple[int | None, list[DomainEvent]]:
        """Get events for a hand, starting from snapshot if available.

        Args:
            hand_id: Hand identifier

        Returns:
            Tuple of (snapshot_version, events) where snapshot_version is None if no snapshot
        """
        snapshot = self.get_snapshot(hand_id)
        if snapshot:
            snapshot_version, _ = snapshot
            events = self.get_events(hand_id, from_version=snapshot_version + 1)
            return snapshot_version, events
        return None, self.get_events(hand_id)

    def get_current_version(self, hand_id: str) -> int:
        """Get current version for a hand.

        Args:
            hand_id: Hand identifier

        Returns:
            Current version (0 if no events)
        """
        db: Session = self.SessionLocal()
        try:
            return self._get_current_version(db, hand_id)
        finally:
            db.close()

    def _get_current_version(self, db: Session, hand_id: str) -> int:
        """Get current version from database session."""
        result = (
            db.query(EventModel.version)
            .filter(EventModel.hand_id == hand_id)
            .order_by(EventModel.version.desc())
            .first()
        )
        return result[0] if result else 0

    def save_snapshot(self, hand_id: str, version: int, state_data: str) -> None:
        """Save a snapshot of game state.

        Args:
            hand_id: Hand identifier
            version: Version at which snapshot was taken
            state_data: JSON serialized GameState
        """
        db: Session = self.SessionLocal()
        try:
            snapshot = HandSnapshotModel(hand_id=hand_id, version=version, state_data=state_data)
            db.merge(snapshot)  # Upsert
            db.commit()
        finally:
            db.close()

    def get_snapshot(self, hand_id: str) -> tuple[int, str] | None:
        """Get latest snapshot for a hand.

        Args:
            hand_id: Hand identifier

        Returns:
            Tuple of (version, state_data) or None if no snapshot
        """
        db: Session = self.SessionLocal()
        try:
            snapshot = (
                db.query(HandSnapshotModel).filter(HandSnapshotModel.hand_id == hand_id).first()
            )
            if snapshot:
                return (snapshot.version, snapshot.state_data)
            return None
        finally:
            db.close()

    def record_command(
        self, idempotency_key: str, hand_id: str, command_type: str, command_data: str
    ) -> bool:
        """Record a command for idempotency checking.

        Args:
            idempotency_key: Unique command identifier
            hand_id: Hand identifier
            command_type: Type of command
            command_data: JSON serialized command

        Returns:
            True if command is new, False if duplicate
        """
        db: Session = self.SessionLocal()
        try:
            existing = (
                db.query(CommandModel)
                .filter(CommandModel.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                return False  # Duplicate

            command = CommandModel(
                idempotency_key=idempotency_key,
                hand_id=hand_id,
                command_type=command_type,
                command_data=command_data,
            )
            db.add(command)
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False  # Duplicate
        finally:
            db.close()

    def get_command_result(self, idempotency_key: str) -> str | None:
        """Get result events for a previously executed command.

        Args:
            idempotency_key: Command idempotency key

        Returns:
            JSON serialized events or None if command not found
        """
        db: Session = self.SessionLocal()
        try:
            command = (
                db.query(CommandModel)
                .filter(CommandModel.idempotency_key == idempotency_key)
                .first()
            )
            return command.result_events if command and command.result_events else None
        finally:
            db.close()

    def update_command_result(self, idempotency_key: str, events_json: str) -> None:
        """Update command with result events.

        Args:
            idempotency_key: Command idempotency key
            events_json: JSON serialized events
        """
        db: Session = self.SessionLocal()
        try:
            command = (
                db.query(CommandModel)
                .filter(CommandModel.idempotency_key == idempotency_key)
                .first()
            )
            if command:
                command.result_events = events_json
                db.commit()
        finally:
            db.close()

    def _serialize_event(self, event: DomainEvent) -> str:
        """Serialize event to JSON."""
        # Simple serialization - in production, use proper event serialization
        data = {
            "type": type(event).__name__,
            "timestamp": event.timestamp,
        }
        # Add event-specific fields
        for field_name, field_value in event.__dict__.items():
            if field_name != "timestamp":
                # Handle special types
                if hasattr(field_value, "__dict__"):
                    data[field_name] = str(field_value)
                elif isinstance(field_value, (set, frozenset)):
                    data[field_name] = list(field_value)
                else:
                    data[field_name] = field_value
        return json.dumps(data)

    def _deserialize_event(self, event_model: EventModel) -> DomainEvent:
        """Deserialize event from JSON."""
        # This is a simplified deserializer
        # In production, use proper event deserialization with type registry
        data = json.loads(event_model.event_data)
        event_type = data.get("type")

        # Import event types
        from engine.domain.events import (
            ActionApplied,
            BettingRoundComplete,
            BlindPosted,
            CardsDealt,
            HandEnded,
            HandStarted,
            PlayerSatDown,
            PlayerStoodUp,
            PotCreated,
            SeedRevealed,
            ShowdownResolved,
            StreetDealt,
        )
        from engine.domain.state import Street

        event_map = {
            "PlayerSatDown": PlayerSatDown,
            "PlayerStoodUp": PlayerStoodUp,
            "HandStarted": HandStarted,
            "SeedRevealed": SeedRevealed,
            "CardsDealt": CardsDealt,
            "BlindPosted": BlindPosted,
            "ActionApplied": ActionApplied,
            "StreetDealt": StreetDealt,
            "BettingRoundComplete": BettingRoundComplete,
            "PotCreated": PotCreated,
            "ShowdownResolved": ShowdownResolved,
            "HandEnded": HandEnded,
        }

        event_class = event_map.get(event_type)
        if not event_class:
            raise ValueError(f"Unknown event type: {event_type}")

        # Reconstruct event (simplified - assumes all fields are in data)
        kwargs = {}
        for k, v in data.items():
            if k == "type":
                continue
            # Handle special types
            if k == "street" and isinstance(v, str):
                # Handle both "PREFLOP" and "Street.PREFLOP" formats
                street_value = v.replace("Street.", "") if "Street." in v else v
                try:
                    kwargs[k] = Street(street_value)
                except ValueError:
                    print(f"[EventStore] Invalid street value: {v}, trying {street_value}")
                    # Fallback: try to extract just the street name
                    if "." in street_value:
                        street_value = street_value.split(".")[-1]
                    kwargs[k] = Street(street_value)
            elif k == "eligible_seats" and isinstance(v, list):
                kwargs[k] = frozenset(v)
            elif k == "winners" and isinstance(v, dict):
                kwargs[k] = {int(k2): int(v2) for k2, v2 in v.items()}
            elif k == "cards" and isinstance(v, list):
                # Cards would need proper deserialization
                # For now, skip (cards are server-only anyway)
                continue
            else:
                kwargs[k] = v

        return event_class(**kwargs)
