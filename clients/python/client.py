"""Python client SDK for Poker Engine API."""

import asyncio
import json
import time
from typing import AsyncIterator, Optional

import websockets
from websockets.client import WebSocketClientProtocol


class PokerClient:
    """Client for interacting with Poker Engine API."""

    def __init__(self, base_url: str = "http://localhost:8000", token: Optional[str] = None):
        """Initialize client.

        Args:
            base_url: Base URL of the API
            token: Optional JWT authentication token
        """
        self.base_url = base_url.rstrip("/")
        self.ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.token = token
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    async def get_table_snapshot(self, table_id: str) -> dict:
        """Get current table snapshot.

        Args:
            table_id: Table identifier

        Returns:
            Table snapshot data
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/v1/tables/{table_id}/snapshot"
            async with session.get(url, headers=self.headers) as response:
                response.raise_for_status()
                return await response.json()

    async def get_hand_events(self, hand_id: str, from_version: int = 0) -> dict:
        """Get events for a hand.

        Args:
            hand_id: Hand identifier
            from_version: Starting version

        Returns:
            Hand events data
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/v1/hands/{hand_id}/events"
            params = {"from_version": from_version}
            async with session.get(url, headers=self.headers, params=params) as response:
                response.raise_for_status()
                return await response.json()

    async def connect_websocket(self, table_id: str) -> WebSocketClientProtocol:
        """Connect to table WebSocket.

        Args:
            table_id: Table identifier

        Returns:
            WebSocket connection
        """
        ws_url = f"{self.ws_url}/ws/tables/{table_id}"
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        return await websockets.connect(ws_url, extra_headers=headers)

    async def watch_table(
        self, table_id: str
    ) -> AsyncIterator[dict]:
        """Watch table for real-time updates.

        Args:
            table_id: Table identifier

        Yields:
            Event messages from the table
        """
        ws = await self.connect_websocket(table_id)
        try:
            async for message in ws:
                data = json.loads(message)
                yield data
        finally:
            await ws.close()

    async def send_command(
        self, table_id: str, command_type: str, command_data: dict, idempotency_key: Optional[str] = None
    ) -> dict:
        """Send a command via WebSocket.

        Args:
            table_id: Table identifier
            command_type: Type of command (sit_down, act, start_hand)
            command_data: Command data
            idempotency_key: Optional idempotency key

        Returns:
            Command response
        """
        ws = await self.connect_websocket(table_id)
        try:
            # Receive initial state
            initial = await ws.recv()
            
            # Send command
            command = {
                "type": command_type,
                "data": command_data,
                "idempotency_key": idempotency_key or f"{command_type}-{time.time()}",
                "expected_version": 0,  # Would need to track this in real implementation
            }
            await ws.send(json.dumps(command))
            
            # Wait for response
            response = await ws.recv()
            return json.loads(response)
        finally:
            await ws.close()

    async def sit_down(
        self, table_id: str, seat_id: int, stack: int, player_id: str
    ) -> dict:
        """Sit down at a table.

        Args:
            table_id: Table identifier
            seat_id: Seat number
            stack: Starting chip stack
            player_id: Player identifier

        Returns:
            Command response
        """
        return await self.send_command(
            table_id,
            "sit_down",
            {"seat_id": seat_id, "stack": stack, "player_id": player_id},
        )

    async def act(
        self,
        table_id: str,
        seat_id: int,
        action_type: str,
        amount: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        expected_version: int = 0,
    ) -> dict:
        """Make a player action.

        Args:
            table_id: Table identifier
            seat_id: Seat number
            action_type: Action type (FOLD, CHECK, CALL, BET, RAISE)
            amount: Amount for BET/RAISE
            idempotency_key: Optional idempotency key
            expected_version: Expected version for optimistic locking

        Returns:
            Command response
        """
        return await self.send_command(
            table_id,
            "act",
            {
                "seat_id": seat_id,
                "action_type": action_type,
                "amount": amount,
                "idempotency_key": idempotency_key or f"act-{time.time()}",
                "expected_version": expected_version,
            },
        )

    async def start_hand(
        self, table_id: str, hand_id: str, seed_commit: str
    ) -> dict:
        """Start a new hand.

        Args:
            table_id: Table identifier
            hand_id: Hand identifier
            seed_commit: Committed seed hash

        Returns:
            Command response
        """
        return await self.send_command(
            table_id,
            "start_hand",
            {"hand_id": hand_id, "seed_commit": seed_commit},
        )


# Example usage
async def example():
    """Example usage of the client."""
    client = PokerClient(token="your-token-here")
    
    # Get table snapshot
    snapshot = await client.get_table_snapshot("table-1")
    print(f"Table state: {snapshot['street']}")
    
    # Watch table for updates
    async for event in client.watch_table("table-1"):
        print(f"Event: {event}")


if __name__ == "__main__":
    asyncio.run(example())

