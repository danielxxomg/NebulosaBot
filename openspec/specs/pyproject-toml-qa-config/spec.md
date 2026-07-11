# pyproject.toml QA Configuration Specification

## Purpose

Configure ruff, mypy, bandit, pytest, and dev dependencies in `pyproject.toml` so that all QA tooling reads its config from a single source of truth and the coverage gate ratchets incrementally across PR slices.

## Requirements

### Requirement: Ruff configuration present

`pyproject.toml` MUST contain a `[tool.ruff]` section configuring linting and formatting rules for the project. The ruff `select` list MUST include the following rule groups in addition to any existing ones: `S` (bandit/security), `C4` (comprehensions), `C90` (mccabe complexity), `RET` (return), `T20` (print), `ARG` (unused arguments), `DTZ` (datetime timezone), `EM` (errmsg), `T10` (debugger), `TRY` (tryceratops), `RSE` (raise), `FLY` (flynt), `PERF` (perflint), `FURB` (refurb). The `[tool.ruff.mccabe]` section MUST set `max-complexity = 15`. Per-file `ignore` rules for test files MUST suppress `S101` (assert), `ARG` rules, and `T20` rules in `tests/`.

#### Scenario: Ruff reads config from pyproject.toml

- GIVEN `[tool.ruff]` is defined in `pyproject.toml`
- WHEN `ruff check` is invoked without explicit config flags
- THEN ruff reads its configuration from `pyproject.toml`

#### Scenario: New rule groups enforced

- GIVEN the ruff `select` list includes `S`, `C4`, `C90`, `RET`, `T20`, `ARG`, `DTZ`, `EM`, `T10`, `TRY`, `RSE`, `FLY`, `PERF`, `FURB`
- WHEN `ruff check bot/` runs
- THEN violations for all 14 new rule groups are reported

#### Scenario: McCabe complexity limit enforced

- GIVEN `[tool.ruff.mccabe]` sets `max-complexity = 15`
- WHEN a function has cyclomatic complexity above 15
- THEN ruff reports a `C901` violation

#### Scenario: Test files exempt from assert and print rules

- GIVEN `tests/` has per-file ignores for `S101`, `ARG`, `T20`
- WHEN `ruff check tests/` runs
- THEN `assert` usage and `print()` calls in tests do not trigger violations

### Requirement: Mypy configuration present

`pyproject.toml` MUST contain a `[tool.mypy]` section with `strict = true`. Per-file `[[tool.mypy.overrides]]` blocks MUST exist ONLY for modules with known tech debt that cannot be resolved without behavioral changes: `bot.cogs.*` (`untyped-decorator`) and `tests.*`. The override blocks for `bot.core.*`, `bot.listeners.*`, and `bot.bot` MUST NOT be present — those modules SHALL pass strict mypy without suppression. Per-file overrides SHOULD NOT suppress `type-arg` for any module whose models have been annotated with explicit generic parameters (e.g., `dict[str, Any]`).

#### Scenario: Mypy strict mode enabled

- GIVEN `strict = true` is set in `[tool.mypy]`
- WHEN mypy runs against the project
- THEN all strict checks are enforced (warn_return_any, warn_unused_configs, disallow_untyped_defs, etc.)

#### Scenario: Only tech-debt overrides remain

- GIVEN `pyproject.toml` contains `[[tool.mypy.overrides]]` blocks
- WHEN the overrides are inspected
- THEN only `bot.cogs.*` (suppressing `untyped-decorator`) and `tests.*` overrides exist
- AND no override block targets `bot.core.*`, `bot.listeners.*`, or `bot.bot`

#### Scenario: bot.core passes strict without suppression

- GIVEN no `[[tool.mypy.overrides]]` block targets `bot.core.*`
- WHEN `mypy --strict bot/core/` runs
- THEN zero errors are reported

#### Scenario: bot.listeners passes strict without suppression

- GIVEN no `[[tool.mypy.overrides]]` block targets `bot.listeners.*`
- WHEN `mypy --strict bot/listeners/` runs
- THEN zero errors are reported

#### Scenario: bot.bot passes strict without suppression

- GIVEN no `[[tool.mypy.overrides]]` block targets `bot.bot`
- WHEN `mypy --strict bot/bot.py` runs
- THEN zero errors are reported (attr-defined resolved via isinstance narrowing)

#### Scenario: bot.models has no type-arg suppression

- GIVEN the `[[tool.mypy.overrides]]` block for `bot.models.*` does not include `type-arg` in `disable_error_code`
- WHEN `mypy --strict bot/models/` runs
- THEN zero `type-arg` errors are reported

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

`pyproject.toml` MUST configure `addopts = "--cov=bot --cov-fail-under=75"` as the final coverage gate.

#### Scenario: Gate at 75%

- GIVEN `addopts` sets `--cov-fail-under=75`
- WHEN `pytest` runs
- THEN the run fails if `bot/` coverage is below 75%

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
