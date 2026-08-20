# Makefile DX Specification

## Purpose

Provide local developer experience targets in a `Makefile` so that common QA commands (`lint`, `type`, `test`, `cov`, `ci`, `audit`, `tach`) are invocable with a single `make` invocation, matching the CI pipeline locally.

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

The `Makefile` MUST provide a `make type` target that runs `uv run ty check bot/ tests/` (ty replaces mypy).

#### Scenario: make type runs ty

- GIVEN the developer runs `make type`
- WHEN the target executes
- THEN `uv run ty check bot/ tests/` runs

#### Scenario: ty error reported

- GIVEN a ty error-severity diagnostic exists
- WHEN `make type` runs
- THEN the target fails and reports the diagnostic

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

The `Makefile` MUST provide a `make ci` target that runs lint, type, test, and cov in sequence, failing fast on the first error. The `security` (bandit) target MUST be removed from the `ci` chain — security is folded into `lint` via Ruff `S` rules.

#### Scenario: make ci runs full pipeline

- GIVEN the developer runs `make ci`
- WHEN the target executes
- THEN lint, type, test, and cov run in order

#### Scenario: make ci fails fast

- GIVEN a lint violation exists
- WHEN the developer runs `make ci`
- THEN the target fails at the lint step and does not proceed to type, test, or cov

### Requirement: Makefile provides audit target via uv

The `Makefile` MUST provide a `make audit` target that runs `uv audit`.

#### Scenario: make audit runs uv audit

- GIVEN the developer runs `make audit`
- WHEN the target executes
- THEN `uv audit` runs and scans dependencies for vulnerabilities

#### Scenario: audit vulnerability reported

- GIVEN a dependency has a known vulnerability
- WHEN `make audit` runs
- THEN the target fails and reports the finding

### Requirement: Makefile provides tach targets

The `Makefile` MUST provide `make tach` (runs `tach check` + `tach check-external`) and MAY provide `make tach-external` (runs `tach check-external` alone).

#### Scenario: make tach runs both checks

- GIVEN the developer runs `make tach`
- WHEN the target executes
- THEN `tach check` and `tach check-external` both run

#### Scenario: tach boundary violation reported

- GIVEN a module imports outside its allowed layer
- WHEN `make tach` runs
- THEN the target fails and reports the violating import

### Requirement: Makefile provides lint-full and type-full triage targets

The `Makefile` MUST retain `make lint-full` and `make type-full` as local triage aliases. `make type-full` MUST run `uv run ty check bot/ tests/` (same as `make type`). `make lint-full` MUST run `uv run ruff check bot/ tests/` and `uv run ruff format --check bot/ tests/`.

#### Scenario: make type-full runs ty on full scope

- GIVEN the developer runs `make type-full`
- WHEN the target executes
- THEN `uv run ty check bot/ tests/` runs

#### Scenario: make lint-full runs ruff on full scope

- GIVEN the developer runs `make lint-full`
- WHEN the target executes
- THEN `ruff check` and `ruff format --check` run against `bot/` and `tests/`
