# Property Tests Specification

## Purpose

Use Hypothesis to verify mathematical invariants of economy functions (`compute_xp_for_level`, `compute_level`) across the full input domain, catching edge cases that example-based tests miss.

## Requirements

### Requirement: Property tests for compute_xp_for_level

Hypothesis property tests MUST verify invariants of `compute_xp_for_level` across all valid level inputs. A discovered counterexample constitutes a bug in the formula.

#### Scenario: XP requirement is always positive

- GIVEN any valid level input (non-negative integer)
- WHEN `compute_xp_for_level(level)` is called
- THEN the result MUST be a positive number

#### Scenario: XP requirement is monotonically increasing

- GIVEN two levels where level_b > level_a
- WHEN `compute_xp_for_level` is called for both
- THEN `compute_xp_for_level(level_b)` MUST be greater than `compute_xp_for_level(level_a)`

### Requirement: Property tests for compute_level

Hypothesis property tests MUST verify invariants of `compute_level` across valid XP inputs.

#### Scenario: Level is non-negative

- GIVEN any valid XP input (non-negative integer)
- WHEN `compute_level(xp)` is called
- THEN the result MUST be a non-negative integer

#### Scenario: Higher XP yields equal or higher level

- GIVEN two XP values where xp_b >= xp_a
- WHEN `compute_level` is called for both
- THEN `compute_level(xp_b)` MUST be >= `compute_level(xp_a)`

### Requirement: Deterministic input domain

Hypothesis strategies MUST constrain inputs to the deterministic domain used by the bot (e.g., levels 0–1000, XP 0–10_000_000). Unbounded integers MUST NOT be used.

#### Scenario: Bounded level input

- GIVEN the Hypothesis strategy for level
- WHEN Hypothesis generates test cases
- THEN all generated levels are within [0, 1000]

#### Scenario: Bounded XP input

- GIVEN the Hypothesis strategy for XP
- WHEN Hypothesis generates test cases
- THEN all generated XP values are within [0, 10_000_000]
