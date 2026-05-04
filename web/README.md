# Poker Engine Web UI

A modern, responsive web interface for the DEAL-R Poker Engine.

## Features

- 🎮 **Real-time Game Updates** - WebSocket connection for live game state
- 🎯 **Interactive Table** - Visual poker table with 9 seats
- 🃏 **Card Display** - Community cards and player cards visualization
- ⚡ **Player Actions** - Fold, Check, Call, Bet, Raise controls
- 📊 **Hand History** - Real-time event log
- 📈 **Player Stats** - Statistics and game information
- 🎨 **Modern Design** - Beautiful, responsive UI

## Usage

### Option 1: Simple HTTP Server

```bash
# From the web directory
cd web
python3 -m http.server 8080

# Or with Node.js
npx http-server -p 8080
```

Then open `http://localhost:8080` in your browser.

### Option 2: Serve with FastAPI

Add this to `server/main.py`:

```python
from fastapi.staticfiles import StaticFiles

app.mount("/web", StaticFiles(directory="web", html=True), name="web")
```

Then access at `http://localhost:8000/web`

### Option 3: Development Server

```bash
# Start the poker engine server
uvicorn server.main:app --reload

# In another terminal, serve the web UI
cd web
python3 -m http.server 8080
```

## How to Use

1. **Connect to Table**
   - Enter your Player ID (e.g., "player1")
   - Enter Table ID (e.g., "table-1")
   - Click "Connect"

2. **Sit Down**
   - Enter seat number (0-8)
   - Enter starting stack
   - Click "Sit Down"

3. **Start a Hand**
   - Enter Hand ID (or leave blank for auto-generated)
   - Enter Seed Commit
   - Click "Start Hand"

4. **Make Actions**
   - When it's your turn, the action panel appears
   - Use buttons: Fold, Check, Call, Bet, Raise
   - For Bet/Raise, enter amount first

5. **Watch the Game**
   - Community cards appear in the center
   - Pots are displayed above the cards
   - Hand history shows all events
   - Player stats update in real-time

## Features in Detail

### Poker Table
- 9 seats arranged around an oval table
- Active seats highlighted in green
- Seat to act highlighted in gold with pulse animation
- Empty seats shown with dashed border

### Community Cards
- Flop, Turn, River cards displayed in center
- Color-coded (red for hearts/diamonds, black for clubs/spades)
- Placeholders shown when cards not yet dealt

### Action Panel
- Appears when it's your turn
- Shows current bet and call amount
- Buttons enabled/disabled based on game state
- Bet amount input for BET/RAISE actions

### Hand History
- Real-time event log
- Shows all game events as they occur
- Timestamp for each event
- Scrollable list

## Customization

### Styling
Edit `styles.css` to customize:
- Colors and themes
- Table appearance
- Card styling
- Layout and spacing

### Functionality
Edit `app.js` to add:
- Additional features
- Custom actions
- Analytics
- Sound effects

## Browser Compatibility

- Chrome/Edge (recommended)
- Firefox
- Safari
- Modern browsers with WebSocket support

## Troubleshooting

**Can't connect?**
- Make sure the server is running on `http://localhost:8000`
- Check browser console for errors
- Verify WebSocket URL is correct

**Actions not working?**
- Make sure you're seated
- Check if it's your turn
- Verify you have enough chips
- Check server logs for errors

**Cards not showing?**
- Check browser console for errors
- Verify server is sending correct data format
- Try refreshing the page

## Development

The UI is built with:
- Vanilla JavaScript (no frameworks)
- Modern CSS (Grid, Flexbox, Animations)
- WebSocket API for real-time updates
- Fetch API for REST calls

Easy to extend and customize!
