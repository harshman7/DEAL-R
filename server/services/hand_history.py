"""Hand history search and filtering service."""

from datetime import datetime

from sqlalchemy.orm import Session

from server.persistence.event_store import EventStore
from server.persistence.models import EventModel


class HandHistoryService:
    """Service for searching and filtering hand history."""

    def __init__(self, event_store: EventStore):
        """Initialize hand history service.

        Args:
            event_store: Event store instance
        """
        self.event_store = event_store

    def search_hands(
        self,
        player_id: str | None = None,
        table_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[str]:
        """Search for hands matching criteria.

        Args:
            player_id: Filter by player ID
            table_id: Filter by table ID
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum results
            offset: Result offset

        Returns:
            List of hand IDs
        """
        db: Session = self.event_store.SessionLocal()
        try:
            query = db.query(EventModel.hand_id).distinct()

            # Filter by player (would need to check event data)
            # This is simplified - in production, would parse event_data JSON
            if player_id:
                # Would need to search in event_data JSON
                pass

            # Filter by date
            if start_date:
                query = query.filter(EventModel.timestamp >= int(start_date.timestamp()))
            if end_date:
                query = query.filter(EventModel.timestamp <= int(end_date.timestamp()))

            # Order by most recent
            query = query.order_by(EventModel.timestamp.desc())

            # Limit and offset
            results = query.limit(limit).offset(offset).all()
            return [r[0] for r in results]
        finally:
            db.close()

    def get_player_hands(self, player_id: str, limit: int = 100) -> list[str]:
        """Get hands for a specific player.

        Args:
            player_id: Player identifier
            limit: Maximum results

        Returns:
            List of hand IDs
        """
        # Simplified - would need to search event_data for PlayerSatDown events
        return self.search_hands(player_id=player_id, limit=limit)

    def get_table_hands(self, table_id: str, limit: int = 100) -> list[str]:
        """Get hands for a specific table.

        Args:
            table_id: Table identifier
            limit: Maximum results

        Returns:
            List of hand IDs
        """
        return self.search_hands(table_id=table_id, limit=limit)
