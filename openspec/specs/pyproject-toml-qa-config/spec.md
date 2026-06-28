# pyproject.toml QA Configuration Specification

## Purpose

Configure ruff, mypy, bandit, pytest, and dev dependencies in `pyproject.toml` so that all QA tooling reads its config from a single source of truth and the coverage gate ratchets incrementally across PR slices.

## Requirements

### Requirement: Ruff configuration present

`pyproject.toml` MUST contain a `[tool.ruff]` section configuring linting and formatting rules for the project.

#### Scenario: Ruff reads config from pyproject.toml

- GIVEN `[tool.ruff]` is defined in `pyproject.toml`
- WHEN `ruff check` is invoked without explicit config flags
- THEN ruff reads its configuration from `pyproject.toml`

### Requirement: Mypy configuration present

`pyproject.toml` MUST contain a `[tool.mypy]` section. It MUST include `disable_error_code = "attr-defined"` to accommodate the `ctx._guild_config` tech debt in `bot/bot.py:256-264`.

#### Scenario: Mypy attr-defined suppressed for guild config

- GIVEN `disable_error_code = "attr-defined"` is set in `[tool.mypy]`
- WHEN mypy encounters `ctx._guild_config` access in `bot/bot.py:256-264`
- THEN mypy does not report an `attr-defined` error for that access

#### Scenario: Other mypy errors still reported

- GIVEN `disable_error_code = "attr-defined"` is set
- WHEN mypy encounters a different type of error (e.g., `no-redef`)
- THEN the error is still reported

### Requirement: Bandit configuration present

`pyproject.toml` MUST contain a `[tool.bandit]` section. It MUST exclude the `tests/` directory from security scanning.

#### Scenario: Bandit skips tests directory

- GIVEN `[tool.bandit]` excludes `tests/`
- WHEN bandit scans the project
- THEN files under `tests/` are not analyzed

#### Scenario: Bandit scans bot source

- GIVEN `[tool.bandit]` excludes only `tests/`
- WHEN bandit scans the project
- THEN files under `bot/` are analyzed for security findings

### Requirement: Coverage gate ratchet in pytest addopts

`pyproject.toml` MUST configure `addopts = "--cov=bot --cov-fail-under=N"` where N is 55 after PR1, 60 after PR2, and 70 after PR3.

#### Scenario: Gate at 55% after PR1

- GIVEN PR1 is merged and `addopts` sets `--cov-fail-under=55`
- WHEN `pytest` runs
- THEN the run fails if `bot/` coverage is below 55%

#### Scenario: Gate raised to 70% after PR3

- GIVEN PR3 is merged and `addopts` sets `--cov-fail-under=70`
- WHEN `pytest` runs
- THEN the run fails if `bot/` coverage is below 70%

### Requirement: Warning filter allowlist

`pyproject.toml` MUST configure `filterwarnings` to suppress known benign warnings (e.g., discord.py's `asyncio.iscoroutinefunction` deprecation) so they do not cause test failures under `PYTHONASYNCIODEBUG=1`.

#### Scenario: Benign asyncio warning suppressed

- GIVEN `filterwarnings` suppresses the `iscoroutinefunction` deprecation
- WHEN tests run with `PYTHONASYNCIODEBUG=1`
- THEN the deprecation warning does not cause a test failure

### Requirement: pytest-randomly adopted with deterministic seed

`pytest-randomly` MUST be added as a dev dependency and MUST randomize test ordering by default. The default seed MUST be deterministic (fixed value) so that CI and local runs produce the same order unless explicitly reseeded.

#### Scenario: Tests run in random order by default

- GIVEN `pytest-randomly` is installed
- WHEN `pytest` runs without specifying a seed
- THEN tests execute in a randomized order using the default deterministic seed

#### Scenario: Deterministic seed produces same order

- GIVEN the default seed is fixed
- WHEN `pytest` runs twice with no code changes
- THEN both runs produce the identical test execution order

### Requirement: Dev dependencies declared

`pyproject.toml` MUST declare the following dev dependencies: ruff, mypy, bandit, pytest-cov, hypothesis, pytest-randomly.

#### Scenario: Dev dependencies installable

- GIVEN `pyproject.toml` lists the required dev dependencies
- WHEN `uv sync --dev` runs
- THEN all QA tools are installed and available
