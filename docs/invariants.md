# Invariants

Invariants are properties that must **always** hold true for valid game states. These are checked in property-based tests to ensure correctness.

## Core Invariants

### 1. No Negative Stacks

**Invariant**: All players have non-negative chip amounts.

```python
∀ player in state.seats:
    player.stack >= 0
    player.committed_street >= 0
    player.committed_total >= 0
```

**Violation**: System error - indicates bug in reducer or event handler.

### 2. Chip Conservation

**Invariant**: Total chips on table remain constant (no rake).

```python
initial_total = sum(player.stack + player.committed_total for all players)
current_total = sum(player.stack + player.committed_total for all players)

initial_total == current_total  # Always true
```

**Note**: In production, rake would be subtracted, but for this engine we assume rake = 0.

### 3. Pot Correctness

**Invariant**: At terminal state (SHOWDOWN/COMPLETE), pots match committed chips.

```python
if state.street in (SHOWDOWN, COMPLETE):
    total_committed = sum(player.committed_total for active players)
    total_pots = sum(pot.amount for pot in state.pots)
    total_committed == total_pots
```

**Violation**: Indicates bug in side pot calculation or event handling.

### 4. Betting State Consistency

**Invariant**: Betting state values are non-negative.

```python
state.current_bet >= 0
state.min_raise >= 0
```

### 5. Player Status Consistency

**Invariant**: Player status matches their chip state.

```python
if player.stack == 0 and player.committed_total > 0:
    player.status == ALL_IN  # Not ACTIVE
```

### 6. Deterministic Replay

**Invariant**: Replaying events produces identical state.

```python
events = event_store.get_events(hand_id)
replay_state = fold(events, initial_state)
reducer_state = # state from reducer

replay_state == reducer_state  # Must be identical
```

## Property-Based Testing

All invariants are tested using **Hypothesis** property-based testing:

- Random valid game states generated
- Random valid action sequences executed
- Invariants checked after each action
- Deterministic replay verified

## Invariant Checking

The `engine/rules/invariants.py` module provides:

- `check_all_invariants()`: Comprehensive check
- `check_chip_conservation()`: Chip conservation
- `check_no_negative_stacks()`: Stack validation
- `check_pot_correctness()`: Pot validation

## Violation Handling

If an invariant is violated:

1. **Development**: Property tests will fail, indicating bug
2. **Production**: Should log error and reject state transition
3. **Recovery**: Replay events from last known good state

## Testing Strategy

1. **Unit Tests**: Test individual invariant checks
2. **Property Tests**: Generate random scenarios, verify invariants
3. **Integration Tests**: Test invariants across full hand flow
4. **Replay Tests**: Verify deterministic replay invariant

