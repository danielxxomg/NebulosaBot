# conftest.py frozen_clock Specification

## Purpose

Provide a `frozen_clock` pytest fixture that freezes `datetime.now(timezone.utc)` to a deterministic value, eliminating date-time flakiness when tests run under randomized ordering with `pytest-randomly`.

## Requirements

### Requirement: frozen_clock fixture available

`tests/conftest.py` MUST expose a `frozen_clock` fixture that freezes `datetime.now(timezone.utc)` to a fixed, deterministic timestamp.

#### Scenario: datetime.now returns frozen value

- GIVEN a test uses the `frozen_clock` fixture
- WHEN the test calls `datetime.now(timezone.utc)`
- THEN the returned timestamp is the deterministic frozen value, not the real wall clock

#### Scenario: Frozen value is consistent across calls

- GIVEN a test uses the `frozen_clock` fixture
- WHEN the test calls `datetime.now(timezone.utc)` multiple times within the same test
- THEN all calls return the identical frozen timestamp

### Requirement: Tests using datetime.now MUST opt in

Any test that calls `datetime.now(timezone.utc)` (directly or via service code) MUST use the `frozen_clock` fixture to ensure determinism under `pytest-randomly`.

#### Scenario: Test without frozen_clock is deterministic by convention

- GIVEN a test does not call `datetime.now` directly and does not invoke code that calls it
- WHEN the test runs under `pytest-randomly`
- THEN the test does not require `frozen_clock` and passes consistently

#### Scenario: Flake detected when frozen_clock is missing

- GIVEN a test relies on `datetime.now` but does not use `frozen_clock`
- WHEN tests run in a different random order under `pytest-randomly`
- THEN the test may produce a different result — this is the flake that `frozen_clock` prevents

### Requirement: Fixture restores real clock after test

The `frozen_clock` fixture MUST restore the real `datetime.now` behavior after the test completes so that subsequent tests are not affected.

#### Scenario: Clock restored after test

- GIVEN a test uses `frozen_clock` and completes
- WHEN the next test runs without `frozen_clock`
- THEN `datetime.now(timezone.utc)` returns the real wall clock time
