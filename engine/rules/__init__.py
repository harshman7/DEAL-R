"""Poker game rules: legality checks, side pots, etc."""

from engine.rules.legality import (
    calculate_action_amount,
    compute_legal_actions,
    get_call_amount,
    get_min_raise_amount,
    is_betting_round_complete,
    is_raise_reopening,
    next_player_to_act,
    validate_action,
)
from engine.rules.invariants import (
    check_all_invariants,
    check_chip_conservation,
    check_no_negative_stacks,
    check_pot_correctness,
)
from engine.rules.sidepots import (
    build_side_pots,
    get_pot_distribution,
    validate_pot_invariant,
)

__all__ = [
    # Legality
    "compute_legal_actions",
    "validate_action",
    "calculate_action_amount",
    "get_call_amount",
    "get_min_raise_amount",
    "is_betting_round_complete",
    "is_raise_reopening",
    "next_player_to_act",
    # Side pots
    "build_side_pots",
    "validate_pot_invariant",
    "get_pot_distribution",
    # Invariants
    "check_all_invariants",
    "check_chip_conservation",
    "check_no_negative_stacks",
    "check_pot_correctness",
]

