# Delta for pyproject-toml-qa-config

## MODIFIED Requirements

### Requirement: Ruff configuration present

`pyproject.toml` MUST contain a `[tool.ruff]` section configuring linting and formatting rules. The declared Ruff dependency MUST resolve to `0.15.20`. The `select` list MUST include `S`, `C4`, `C90`, `RET`, `T20`, `ARG`, `DTZ`, `EM`, `T10`, `TRY`, `RSE`, `FLY`, `PERF`, and `FURB`. `[tool.ruff.mccabe]` MUST set `max-complexity = 15`. Test files MUST retain `S101`, `ARG`, and `T20` exceptions. Production per-file ignores MUST NOT retain broad `RSE`, `RET`, or `SIM` suppressions; the broad `TRY` suppression MUST be replaced with explicit residual codes, with `TRY003` deferred when necessary.

#### Scenario: Ruff reads config from pyproject.toml

- GIVEN `[tool.ruff]` is defined in `pyproject.toml`
- WHEN `ruff check` is invoked without explicit config flags
- THEN ruff reads its configuration from `pyproject.toml`

#### Scenario: New rule groups enforced

- GIVEN the ruff `select` list includes the required rule groups
- WHEN `ruff check bot/` runs
- THEN violations for selected groups are reported

#### Scenario: Ruff version is aligned

- GIVEN the project dependency and lockfile resolve Ruff `0.15.20`
- WHEN the QA environment installs development dependencies
- THEN the configured formatter and linter version is `0.15.20`

#### Scenario: McCabe complexity limit enforced

- GIVEN `[tool.ruff.mccabe]` sets `max-complexity = 15`
- WHEN a function has cyclomatic complexity above 15
- THEN ruff reports a `C901` violation

#### Scenario: Test files exempt from assert and print rules

- GIVEN `tests/` has per-file ignores for `S101`, `ARG`, and `T20`
- WHEN `ruff check tests/` runs
- THEN test assertions and prints do not trigger those violations

#### Scenario: Ratcheted production configuration is clean

- GIVEN broad `RSE`, `RET`, `SIM`, and `TRY` ignores are absent or replaced by explicit residual codes
- WHEN `uv run ruff check bot tests` runs
- THEN it exits successfully with zero findings

### Requirement: Mypy configuration present

`pyproject.toml` MUST contain `[tool.mypy]` with `strict = true`. Overrides MUST exist only for known `bot.cogs.*` decorator debt and `tests.*`; overrides for `bot.core.*`, `bot.listeners.*`, and `bot.bot` MUST NOT exist. Per-file overrides SHOULD NOT suppress `type-arg` for explicitly parameterized models. `NebulosaContext` and cog callbacks MUST use `commands.Context[NebulosaBot]` or an equivalent parameterized custom context. New `type: ignore[arg-type]` comments MUST NOT hide decorator inference errors.

#### Scenario: Mypy strict mode enabled

- GIVEN `strict = true` is set
- WHEN mypy runs against the project
- THEN strict checks are enforced

#### Scenario: Only tech-debt overrides remain

- GIVEN mypy override blocks are inspected
- WHEN the configured modules are listed
- THEN only `bot.cogs.*` and `tests.*` overrides remain
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
- THEN zero errors are reported (attr-defined resolved via narrowing)

#### Scenario: bot.models has no type-arg suppression

- GIVEN the `[[tool.mypy.overrides]]` block for `bot.models.*` does not include `type-arg` in `disable_error_code`
- WHEN strict mypy checks `bot/models/`
- THEN zero `type-arg` errors are reported

#### Scenario: Callbacks use the concrete bot context

- GIVEN a hybrid callback accepts `NebulosaContext` or `commands.Context[NebulosaBot]`
- WHEN mypy resolves the command decorator
- THEN decorator inference succeeds without an `arg-type` suppression

#### Scenario: Full bot and test gate is clean

- GIVEN callbacks use the parameterized bot context
- WHEN `mypy bot` runs (tests.* deferred to S2 — `mypy bot tests` remains aspirational with 28 inventoried errors)
- THEN `mypy bot` reports zero errors without adding `type: ignore[arg-type]` to core cogs (tests.* debt is explicit S2 deferral; utility/sentinel hybrid stubs use override arg-type)
