"""Full Hypothesis property test battery for economy math functions.

Tests mathematical invariants of ``compute_xp_for_level`` and
``compute_level`` across the full deterministic domain.

Requirements from spec:
    - XP threshold ≥ 0 for any level in [0, 1000]
    - Higher level → higher XP threshold (monotonic)
    - Level ≥ 0 for any XP in [0, 10_000_000]
    - Higher XP → equal or higher level (monotonic)

TDD cycle: RED → GREEN — tests specify invariants of existing pure functions.
"""

from __future__ import annotations

import sys

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from bot.services.economy_service import EconomyService

# Deterministic domain per spec.
LEVEL_STRATEGY = st.integers(min_value=0, max_value=1000)
XP_STRATEGY = st.integers(min_value=0, max_value=10_000_000)
BASE_STRATEGY = st.integers(min_value=1, max_value=1000)
MULTIPLIER_STRATEGY = st.floats(min_value=1.01, max_value=10.0, allow_nan=False, allow_infinity=False)


@given(level=LEVEL_STRATEGY, base=BASE_STRATEGY, multiplier=MULTIPLIER_STRATEGY)
@settings(max_examples=200, deadline=None)
def test_compute_xp_for_level_positive(level, base, multiplier):
    """XP threshold for any level >= 0 must be non-negative."""
    result = EconomyService.compute_xp_for_level(level, base, multiplier)
    assert result >= 0


@given(
    level_a=st.integers(min_value=0, max_value=999),
    level_b=st.integers(min_value=1, max_value=1000),
    base=BASE_STRATEGY,
    multiplier=MULTIPLIER_STRATEGY,
)
@settings(max_examples=200, deadline=None)
def test_compute_xp_for_level_monotonic(level_a, level_b, base, multiplier):
    """Higher level → higher XP threshold."""
    assume(level_b > level_a)
    xp_a = EconomyService.compute_xp_for_level(level_a, base, multiplier)
    xp_b = EconomyService.compute_xp_for_level(level_b, base, multiplier)
    # Skip overflow cases where both return float max sentinel.
    assume(xp_a < sys.float_info.max)
    assert xp_b > xp_a


@given(xp=XP_STRATEGY, base=BASE_STRATEGY, multiplier=MULTIPLIER_STRATEGY)
@settings(max_examples=200, deadline=None)
def test_compute_level_non_negative(xp, base, multiplier):
    """Level must be >= 0 for any valid XP."""
    result = EconomyService.compute_level(xp, base, multiplier)
    assert result >= 0


@given(
    xp_a=XP_STRATEGY,
    xp_b=XP_STRATEGY,
    base=BASE_STRATEGY,
    multiplier=MULTIPLIER_STRATEGY,
)
@settings(max_examples=200, deadline=None)
def test_compute_level_monotonic(xp_a, xp_b, base, multiplier):
    """Higher XP → equal or higher level."""
    assume(xp_b >= xp_a)
    level_a = EconomyService.compute_level(xp_a, base, multiplier)
    level_b = EconomyService.compute_level(xp_b, base, multiplier)
    assert level_b >= level_a
