"""Proof-of-pattern hypothesis smoke tests for economy math functions.

PR1 scaffold: 2-3 property tests proving hypothesis wiring works.
PR3 will extend this with a full battery.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from bot.services.economy_service import EconomyService

# NOTE: level capped at 100 for smoke test to avoid float overflow
# at extreme multiplier * level combos (10.0^309).  PR3 full battery
# will include the [0, 1000] range after a production overflow guard.
level_strategy = st.integers(min_value=0, max_value=100)
xp_strategy = st.integers(min_value=0, max_value=10_000_000)
base_strategy = st.integers(min_value=1, max_value=1000)
multiplier_strategy = st.floats(min_value=1.01, max_value=10.0, allow_nan=False, allow_infinity=False)


@given(level=level_strategy, base=base_strategy, multiplier=multiplier_strategy)
@settings(max_examples=50, deadline=None)
def test_compute_xp_for_level_zero_returns_zero(level, base, multiplier):
    """compute_xp_for_level(0, ...) must return exactly 0 XP."""
    result = EconomyService.compute_xp_for_level(0, base, multiplier)
    assert result == 0


@given(level=level_strategy, base=base_strategy, multiplier=multiplier_strategy)
@settings(max_examples=50, deadline=None)
def test_compute_xp_for_level_positive(level, base, multiplier):
    """XP threshold for any level >= 0 must be non-negative."""
    result = EconomyService.compute_xp_for_level(level, base, multiplier)
    assert result >= 0


@given(xp=xp_strategy, base=base_strategy, multiplier=multiplier_strategy)
@settings(max_examples=50, deadline=None)
def test_compute_level_non_negative(xp, base, multiplier):
    """Level must be >= 0 for any valid XP input."""
    result = EconomyService.compute_level(xp, base, multiplier)
    assert result >= 0
