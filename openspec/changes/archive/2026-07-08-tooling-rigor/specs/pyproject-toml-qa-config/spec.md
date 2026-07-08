# Delta for pyproject.toml QA Configuration

## MODIFIED Requirements

### Requirement: Ruff configuration present

`pyproject.toml` MUST contain a `[tool.ruff]` section configuring linting and formatting rules for the project. The ruff `select` list MUST include the following rule groups in addition to any existing ones: `S` (bandit/security), `C4` (comprehensions), `C90` (mccabe complexity), `RET` (return), `T20` (print), `ARG` (unused arguments), `DTZ` (datetime timezone), `EM` (errmsg), `T10` (debugger), `TRY` (tryceratops), `RSE` (raise), `FLY` (flynt), `PERF` (perflint), `FURB` (refurb). The `[tool.ruff.mccabe]` section MUST set `max-complexity = 15`. Per-file `ignore` rules for test files MUST suppress `S101` (assert), `ARG` rules, and `T20` rules in `tests/`.

(Previously: ruff config existed but had no explicit rule group selection beyond defaults)

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

`pyproject.toml` MUST contain a `[tool.mypy]` section with `strict = true`. The `attr-defined` error code MUST be suppressed only via per-file `[[tool.mypy.overrides]]` blocks targeting specific modules with known tech debt (e.g., `bot/bot.py`), NOT via a project-wide `disable_error_code`.

(Previously: mypy had `disable_error_code = "attr-defined"` project-wide and no strict mode)

#### Scenario: Mypy strict mode enabled

- GIVEN `strict = true` is set in `[tool.mypy]`
- WHEN mypy runs against the project
- THEN all strict checks are enforced (warn_return_any, warn_unused_configs, disallow_untyped_defs, etc.)

#### Scenario: attr-defined suppressed per-file only

- GIVEN a `[[tool.mypy.overrides]]` block suppresses `attr-defined` for `bot.bot`
- WHEN mypy encounters `ctx._guild_config` access in `bot/bot.py`
- THEN mypy does not report an `attr-defined` error for that module

#### Scenario: attr-defined still reported elsewhere

- GIVEN the override targets only `bot.bot`
- WHEN mypy encounters an `attr-defined` error in another module
- THEN the error IS reported

### Requirement: Coverage gate ratchet in pytest addopts

`pyproject.toml` MUST configure `addopts = "--cov=bot --cov-fail-under=75"` as the final coverage gate.

(Previously: gate was 70 after PR3)

#### Scenario: Gate at 75%

- GIVEN `addopts` sets `--cov-fail-under=75`
- WHEN `pytest` runs
- THEN the run fails if `bot/` coverage is below 75%
