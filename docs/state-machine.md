# State Machine

## Game State Transitions

The poker game follows a well-defined state machine:

```
WAITING → PREFLOP → FLOP → TURN → RIVER → SHOWDOWN → COMPLETE
```

## State Definitions

### WAITING
- Initial state before hand starts
- Players can sit down/stand up
- No active hand

### PREFLOP
- Hand has started
- Blinds posted
- Hole cards dealt (server-only)
- Betting round active

### FLOP
- First three community cards dealt
- Betting round active

### TURN
- Fourth community card dealt
- Betting round active

### RIVER
- Fifth community card dealt
- Final betting round

### SHOWDOWN
- All betting complete
- Hands evaluated
- Pots distributed

### COMPLETE
- Hand finished
- Winners determined
- Ready for next hand

## Transitions

### WAITING → PREFLOP
- **Trigger**: `StartHand` command
- **Conditions**:
  - At least 2 active players
  - Street == WAITING
- **Events**: `HandStarted`

### PREFLOP → FLOP
- **Trigger**: Betting round complete (auto-advance)
- **Conditions**:
  - All active players acted
  - All committed equally
  - Action returned to last aggressor
- **Events**: `BettingRoundComplete`, `StreetDealt(FLOP)`

### FLOP → TURN
- **Trigger**: Betting round complete (auto-advance)
- **Events**: `BettingRoundComplete`, `StreetDealt(TURN)`

### TURN → RIVER
- **Trigger**: Betting round complete (auto-advance)
- **Events**: `BettingRoundComplete`, `StreetDealt(RIVER)`

### RIVER → SHOWDOWN
- **Trigger**: Betting round complete (auto-advance)
- **Events**: `BettingRoundComplete`
- **Actions**: Hand evaluation, pot splitting

### SHOWDOWN → COMPLETE
- **Trigger**: Pots distributed
- **Events**: `ShowdownResolved`, `HandEnded`

## Early Termination

### Single Player Win
- **Trigger**: Only one active player remains
- **Transition**: Current street → COMPLETE
- **Events**: `ShowdownResolved`, `HandEnded(reason="FOLD")`

### All-In Fast-Forward
- **Trigger**: All players all-in
- **Action**: Deal remaining streets immediately
- **Events**: Multiple `StreetDealt` events, then `ShowdownResolved`

## Player State Machine

```
OUT → ACTIVE → FOLDED
           ↓
        ALL_IN
```

- **OUT**: Not in hand (not seated or sitting out)
- **ACTIVE**: In hand, can act
- **FOLDED**: Folded this hand
- **ALL_IN**: All chips committed

## Betting Round State

Each street has a betting round with states:

```
No Bet → Bet Placed → Action Rotation → Round Complete
```

- **No Bet**: `current_bet == 0`
- **Bet Placed**: `current_bet > 0`, `last_raiser_seat` set
- **Action Rotation**: Players act in order
- **Round Complete**: All acted, committed equally

## State Invariants

At all times, the following invariants must hold:

1. No negative stacks
2. Chip conservation: `sum(stack + committed_total)` constant
3. Pot correctness: At terminal state, `sum(pots) == sum(committed_total)`
4. Player status consistency: `stack == 0` → `status == ALL_IN` (if in hand)
