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

**Phase 0-1 Complete**: Core domain models and project structure
- ✅ Project bootstrap (pyproject.toml, docker-compose)
- ✅ Domain models (Card, Deck, PlayerState, GameState)
- ✅ Unit tests for serialization and determinism

**Next**: Phase 2 - Commands, events, and reducer skeleton

## Determinism & Event Sourcing

The engine is designed for deterministic replay:

1. **Seeded RNG**: Deck shuffling uses a committed seed
2. **Event Log**: All state changes are events
3. **Pure Reducer**: `next(state, command) -> (new_state, events[])`
4. **Replay**: Applying events in order reproduces exact state

Given:
- Initial state
- Seed commit/reveal
- Event log

The final state is **guaranteed identical** across replays.

## License

MIT
