# DEAL-R: Event-Sourced Poker Engine

A portfolio-grade, event-sourced No-Limit Texas Hold'em poker engine with deterministic replay, built with Python 3.12, FastAPI, and PostgreSQL.

## Features

- **Event Sourcing**: All game state changes are captured as events
- **Deterministic Replay**: Given the same seed and command log, replay produces identical final state
- **Pure Engine**: Core game logic is IO-free and fully testable
- **Server Authoritative**: All actions validated server-side
- **Idempotent Commands**: Duplicate commands are safely ignored
- **Optimistic Concurrency**: Version-based conflict detection

## Architecture

```
poker-engine/
├── engine/           # Pure deterministic reducer (no IO)
│   ├── domain/       # GameState, PlayerState, Card, Deck
│   ├── rules/        # Legality checks, side pot calculation
│   ├── reducer/      # Event-sourced state transitions
│   ├── eval/         # Hand evaluation
│   └── rng/          # Deterministic RNG
├── server/           # FastAPI REST + WebSocket adapters
│   ├── api/          # REST and WebSocket endpoints
│   ├── persistence/  # Event store, snapshots
│   └── services/     # Business logic orchestration
├── tools/            # CLI tools (replay, hand history)
└── tests/            # Unit + property-based tests
```

## Quick Start

### Prerequisites

- Python 3.11+ (tested with 3.11.5)
- Docker and Docker Compose (for PostgreSQL)

### Setup

1. **Clone and install dependencies:**

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

2. **Start PostgreSQL:**

```bash
docker-compose up -d
```

3. **Run tests:**

```bash
pytest
```

4. **Start the server:**

```bash
uvicorn server.main:app --reload
```

The API will be available at `http://localhost:8000`

- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

## Development

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=engine --cov=server

# Property-based tests only
pytest tests/property/
```

### Code Quality

```bash
# Format code
black .

# Lint
ruff check .

# Type check
mypy engine server
```

### Pre-commit Hooks

```bash
pre-commit install
```

## Project Status

**✅ All Phases Complete**: Full event-sourced poker engine with server

- ✅ Phase 0-1: Core domain models and project structure
- ✅ Phase 2: Commands, events, and reducer skeleton
- ✅ Phase 3: Betting legality and round completion
- ✅ Phase 4: Side pot calculation
- ✅ Phase 5: Auto-advance, dealing, and showdown
- ✅ Phase 6: Invariants and property-based tests
- ✅ Phase 7: FastAPI server with event store and WebSocket
- ✅ Phase 8: CLI tools and documentation

## Determinism & Event Sourcing

The engine is designed for **deterministic replay**:

1. **Seeded RNG**: Deck shuffling uses a committed seed
2. **Event Log**: All state changes are events (append-only)
3. **Pure Reducer**: `next_state(state, command) -> (new_state, events[])`
4. **Replay**: Applying events in order reproduces exact state

Given:
- Initial state
- Seed commit/reveal
- Event log

The final state is **guaranteed identical** across replays.

### Demo: Deterministic Replay

```python
# Example: Replay a hand and verify determinism
from engine.domain.state import GameState
from engine.reducer.reducer import apply_event
from server.persistence.event_store import EventStore

# Load events from database
event_store = EventStore("sqlite:///./poker.db")
events = event_store.get_events("hand-123")

# Replay events
state = GameState(num_seats=9)
for event in events:
    state = apply_event(state, event)

# State is identical to reducer-produced state
print(f"Final street: {state.street}")
print(f"Total pot: {sum(p.amount for p in state.pots)}")
```

### Demo: CLI Tools

```bash
# Replay a hand and get state hash
python -m tools.replay_cli hand-123

# Export hand history
python -m tools.hh_export hand-123 --output hand_history.txt

# Get state hash only (for verification)
python -m tools.replay_cli hand-123 --hash-only
```

### Demo: WebSocket Real-Time Updates

```python
import asyncio
import websockets
import json

async def watch_table(table_id: str):
    uri = f"ws://localhost:8000/ws/tables/{table_id}"
    async with websockets.connect(uri) as websocket:
        # Receive initial state
        initial = await websocket.recv()
        print(f"Initial state: {json.loads(initial)}")
        
        # Listen for events
        while True:
            event = await websocket.recv()
            print(f"Event: {json.loads(event)}")

# Run: asyncio.run(watch_table("table-1"))
```

## Documentation

- **[Architecture](docs/architecture.md)**: System design and event sourcing
- **[State Machine](docs/state-machine.md)**: Game state transitions
- **[Invariants](docs/invariants.md)**: Properties that must always hold
- **[Threat Model](docs/threat-model.md)**: Security considerations
- **[ADR 0001](docs/adr/0001-event-sourcing.md)**: Event sourcing decision record

## License

MIT
