# ADR 0001: Event Sourcing Architecture

## Status

Accepted

## Context

We need a poker engine that:
- Supports deterministic replay
- Provides complete auditability
- Enables time-travel debugging
- Handles concurrent commands safely
- Maintains data integrity

## Decision

Use **event sourcing** architecture:

- All state changes captured as **events**
- State is **derived** by replaying events
- Events stored in append-only log
- Commands are **idempotent**
- Optimistic concurrency control

## Architecture

### Command → Event Flow

```
Command → Reducer → Events → EventStore → State (replay)
```

### Key Components

1. **Commands**: User intentions (SitDown, Act, StartHand)
2. **Events**: Facts that happened (PlayerSatDown, ActionApplied)
3. **Reducer**: Pure function `next_state(state, command) -> (state, events)`
4. **Event Store**: Append-only log with versioning
5. **State**: Derived by replaying events

## Consequences

### Positive

- ✅ **Deterministic**: Same events → same state
- ✅ **Auditable**: Complete history of all actions
- ✅ **Debuggable**: Replay any point in time
- ✅ **Scalable**: Events can be replayed on different machines
- ✅ **Idempotent**: Duplicate commands safe
- ✅ **Concurrent**: Optimistic locking handles conflicts

### Negative

- ⚠️ **Complexity**: More moving parts than CRUD
- ⚠️ **Storage**: Event log grows over time (mitigated by snapshots)
- ⚠️ **Replay Cost**: Reconstructing state requires replaying events

### Mitigations

- **Snapshots**: Optional snapshots for performance
- **Event Compression**: Can compress old events
- **Caching**: Cache reconstructed state

## Alternatives Considered

### 1. Traditional CRUD

**Rejected because**:
- No deterministic replay
- Harder to audit
- Race conditions harder to handle

### 2. CQRS (Command Query Responsibility Segregation)

**Not chosen because**:
- Adds complexity without clear benefit for this use case
- Event sourcing already provides separation

## Implementation Notes

- Events are **immutable** (frozen dataclasses)
- Reducer is **pure** (no side effects)
- Event store uses **optimistic concurrency** (version numbers)
- Commands include **idempotency_key** for duplicate prevention

## References

- Event Sourcing pattern: https://martinfowler.com/eaaDev/EventSourcing.html
- Domain-Driven Design: Event Sourcing chapter

