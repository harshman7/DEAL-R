"""Table management service for multi-table support."""

from server.persistence.event_store import EventStore
from server.services.table_service import TableService


class TableManager:
    """Manages multiple poker tables."""

    def __init__(self, event_store: EventStore):
        """Initialize table manager.

        Args:
            event_store: Event store instance
        """
        self.event_store = event_store
        self._tables: dict[str, TableService] = {}

    def get_table(self, table_id: str) -> TableService:
        """Get or create a table service.

        Args:
            table_id: Table identifier

        Returns:
            TableService instance
        """
        if table_id not in self._tables:
            self._tables[table_id] = TableService(self.event_store, table_id=table_id)
        return self._tables[table_id]

    def list_tables(self) -> list[str]:
        """List all active tables.

        Returns:
            List of table IDs
        """
        return list(self._tables.keys())

    def table_exists(self, table_id: str) -> bool:
        """Check if table exists.

        Args:
            table_id: Table identifier

        Returns:
            True if table exists
        """
        return table_id in self._tables
