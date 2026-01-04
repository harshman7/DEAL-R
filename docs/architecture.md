# Architecture

## Overview

The poker engine is built using **event sourcing** architecture, ensuring deterministic replay and complete auditability. The system is divided into two main layers:

1. **Engine Layer** (Pure, IO-free)
2. **Server Layer** (IO, persistence, networking)

## Architecture Layers

### Engine Layer (`engine/`)

The engine is **pure** - no database, no network, no side effects. It consists of:

- **Domain Models** (`engine/domain/`): Core business entities
  - `state.py`: GameState, PlayerState, Pot
  - `types.py`: Card, Deck, Money, SeatId
  - `commands.py`: Command types (SitDown, Act, StartHand, etc.)
  - `events.py`: Domain events (HandStarted, ActionApplied, etc.)

- **Rules** (`engine/rules/`): Business logic
  - `legality.py`: Betting legality checks, round completion
  - `sidepots.py`: Side pot calculation
  - `invariants.py`: State invariant validation

- **Reducer** (`engine/reducer/`): State transitions
  - `reducer.py`: `next_state(state, command) -> (new_state, events[])`
  - `autoadvance.py`: Automatic game progression

- **Evaluation** (`engine/eval/`): Hand evaluation
  - `evaluator.py`: Poker hand ranking and pot splitting

### Server Layer (`server/`)

The server provides IO adapters:

- **Persistence** (`server/persistence/`): Event store
  - `event_store.py`: Append-only event log with optimistic concurrency
  - `models.py`: SQLAlchemy models

- **API** (`server/api/`): HTTP and WebSocket endpoints
  - `rest.py`: REST API (table snapshot, hand events)
  - `ws.py`: WebSocket API (real-time updates)
  - `schemas.py`: Pydantic request/response models

- **Services** (`server/services/`): Business orchestration
  - `table_service.py`: Command processing, event persistence
  - `auth.py`: Authentication (stub for play-money)

## Event Sourcing

### Command Flow

```
Client → Command → TableService → Reducer → Events → EventStore → Broadcast
```

1. Client sends command with `idempotency_key` and `expected_version`
2. TableService checks idempotency (duplicate commands ignored)
3. Reducer processes command, emits events
4. Events appended to event store with optimistic concurrency
5. Events broadcast to all connected clients

### State Reconstruction

State is **never stored directly**. Instead:

1. Load events from event store
2. Replay events in order: `state = fold(events, initial_state)`
3. Result is identical to reducer-produced state (deterministic)

### Determinism

Given:
- Initial state
- Seed commit/reveal
- Event log

The final state is **guaranteed identical** across replays.

## Data Flow

### Command Processing

```
┌─────────┐
│ Client  │
└────┬────┘
     │ Command (idempotency_key, expected_version)
     ▼
┌─────────────────┐
│ TableService    │
│  - Check idemp. │
│  - Get state    │
└────┬────────────┘
     │
     ▼
┌─────────────────┐
│ Reducer         │
│ next_state()    │
└────┬────────────┘
     │ (new_state, events)
     ▼
┌─────────────────┐
│ EventStore      │
│ append_events() │
│ (optimistic CC) │
└────┬────────────┘
     │
     ▼
┌─────────────────┐
│ Broadcast       │
│ (WebSocket)     │
└─────────────────┘
```

### State Replay

```
┌──────────────┐
│ EventStore   │
│ get_events() │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Replay Loop  │
│ for event:   │
│   state =    │
│   apply_event│
│   (state,    │
│    event)    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Final State  │
└──────────────┘
```

## Key Design Decisions

1. **Pure Engine**: Engine has no dependencies on server layer
2. **Event Sourcing**: All state changes are events
3. **Optimistic Concurrency**: Version-based conflict detection
4. **Idempotent Commands**: Duplicate commands safely ignored
5. **Deterministic**: Same inputs → same outputs

## Technology Stack

- **Language**: Python 3.11+
- **Web Framework**: FastAPI
- **Database**: PostgreSQL (SQLite for development)
- **ORM**: SQLAlchemy 2.0
- **Validation**: Pydantic v2
- **Testing**: pytest + Hypothesis

