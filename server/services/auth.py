"""Minimal authentication stub for play-money."""

from typing import Optional


def get_player_id(token: Optional[str] = None) -> str:
    """Get player ID from token (stub implementation).

    Args:
        token: Authentication token (optional for play-money)

    Returns:
        Player ID (defaults to "anonymous" if no token)
    """
    if token:
        # In real implementation, validate token and extract player_id
        return f"player_{token[:8]}"
    return "anonymous"


def verify_player_can_act(player_id: str, seat_id: int, state) -> bool:
    """Verify player can act at seat (stub implementation).

    Args:
        player_id: Player identifier
        seat_id: Seat number
        state: Game state

    Returns:
        True if player can act (always True for play-money stub)
    """
    # In real implementation, check that player_id matches seat owner
    return True

