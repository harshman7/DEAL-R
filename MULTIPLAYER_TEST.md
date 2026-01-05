# Testing Multiplayer from Different Browsers

## How to Test

### Step 1: Start the Server
```bash
uvicorn server.main:app --reload
```

### Step 2: Open Two Browsers

**Browser 1 (Player 1):**
1. Go to `http://localhost:8000` (redirects to login)
2. Register/Login as user1
3. Enter Table ID: `table-1`
4. Click "Connect to Table"
5. Click "Sit Down" (with your stack)

**Browser 2 (Player 2):**
1. Go to `http://localhost:8000` (in a different browser or incognito)
2. Register/Login as user2 (different account)
3. Enter Table ID: `table-1` (same table!)
4. Click "Connect to Table"
5. Click "Sit Down" (with your stack)

### Step 3: Verify

**What you should see:**
- Both browsers show the same table state
- Both browsers show both players seated
- When Player 1 sits down, Player 2 sees it immediately
- When Player 2 sits down, Player 1 sees it immediately
- Both can see the same player count
- Both can see the same seats

### Step 4: Start a Hand

Once both players are seated:
- Either player can click "Start Hand"
- Both browsers will see the hand start
- Both browsers will see the same game state

## Real-Time Updates

The system uses WebSocket broadcasting:
- When one player sits down → All connected players see it
- When one player acts → All connected players see it
- When a hand starts → All connected players see it
- State is synchronized in real-time

## Troubleshooting

**Players don't see each other?**
- Make sure both are connected to the same Table ID
- Check browser console for WebSocket errors
- Verify both are logged in with different accounts

**State not updating?**
- Check WebSocket connection status (should be "Connected")
- Refresh the page if needed
- Check server logs for errors

