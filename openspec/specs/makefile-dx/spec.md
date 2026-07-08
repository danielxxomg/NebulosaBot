# Makefile DX Specification

## Purpose

Provide local developer experience targets in a `Makefile` so that common QA commands (`lint`, `type`, `test`, `cov`, `ci`) are invocable with a single `make` invocation, matching the CI pipeline locally.

## Requirements

### Requirement: Makefile provides lint target

The `Makefile` MUST provide a `make lint` target that runs ruff check and ruff format --check.

#### Scenario: make lint runs ruff

- GIVEN the developer runs `make lint`
- WHEN the target executes
- THEN ruff check and ruff format --check run against the project

#### Scenario: Lint failure reported

- GIVEN a lint violation exists
- WHEN the developer runs `make lint`
- THEN the target fails and reports the violation

### Requirement: Makefile provides type target

The `Makefile` MUST provide a `make type` target that runs mypy.

#### Scenario: make type runs mypy

- GIVEN the developer runs `make type`
- WHEN the target executes
- THEN mypy runs against the project

### Requirement: Makefile provides test target

The `Makefile` MUST provide a `make test` target that runs pytest.

#### Scenario: make test runs pytest

- GIVEN the developer runs `make test`
- WHEN the target executes
- THEN pytest runs the full test suite

### Requirement: Makefile provides cov target

The `Makefile` MUST provide a `make cov` target that runs pytest with coverage, displays the coverage report, and enforces a 75% coverage floor via `--cov-fail-under=75`.

#### Scenario: make cov shows coverage

- GIVEN the developer runs `make cov`
- WHEN the target executes
- THEN pytest runs with `--cov=bot` and displays a coverage summary

#### Scenario: make cov enforces 75% gate

- GIVEN the developer runs `make cov`
- WHEN total `bot/` coverage is below 75%
- THEN the target fails with a coverage shortfall message

### Requirement: Makefile provides ci target

The `Makefile` MUST provide a `make ci` target that runs lint, type, test, cov, and bandit in sequence, failing fast on the first error.

#### Scenario: make ci runs full pipeline

- GIVEN the developer runs `make ci`
- WHEN the target executes
- THEN lint, type, test, cov, and bandit run in order

#### Scenario: make ci fails fast

- GIVEN a lint violation exists
- WHEN the developer runs `make ci`
- THEN the target fails at the lint step and does not proceed to type, test, cov, or bandit
