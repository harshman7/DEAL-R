"""Analytics service for poker statistics."""

from server.persistence.event_store import EventStore
from server.services.hand_history import HandHistoryService


class AnalyticsService:
    """Service for poker analytics and statistics."""

    def __init__(self, event_store: EventStore):
        """Initialize analytics service.

        Args:
            event_store: Event store instance
        """
        self.event_store = event_store
        self.hand_history = HandHistoryService(event_store)

    def get_player_stats(self, player_id: str) -> dict:
        """Get statistics for a player.

        Args:
            player_id: Player identifier

        Returns:
            Dictionary with player statistics
        """
        hands = self.hand_history.get_player_hands(player_id, limit=1000)

        # Simplified stats - would need to analyze events
        return {
            "player_id": player_id,
            "total_hands": len(hands),
            "hands_played": len(hands),  # Would calculate from events
            "hands_won": 0,  # Would calculate from ShowdownResolved events
            "total_profit": 0,  # Would calculate from stack changes
        }

    def get_table_stats(self, table_id: str) -> dict:
        """Get statistics for a table.

        Args:
            table_id: Table identifier

        Returns:
            Dictionary with table statistics
        """
        hands = self.hand_history.get_table_hands(table_id, limit=1000)

        return {
            "table_id": table_id,
            "total_hands": len(hands),
            "active_players": 0,  # Would calculate from current state
        }

    def get_hand_summary(self, hand_id: str) -> dict:
        """Get summary statistics for a hand.

        Args:
            hand_id: Hand identifier

        Returns:
            Dictionary with hand summary
        """
        events = self.event_store.get_events(hand_id)

        # Analyze events to extract summary
        summary = {
            "hand_id": hand_id,
            "total_events": len(events),
            "players": [],
            "final_pot": 0,
            "winner": None,
        }

        # Would parse events to extract details
        for event in events:
            if hasattr(event, "winners"):
                summary["winner"] = list(event.winners.keys())[0] if event.winners else None

        return summary
