# Delta for pyproject.toml QA Configuration

## MODIFIED Requirements

### Requirement: Mypy configuration present

`pyproject.toml` MUST contain a `[tool.mypy]` section with `strict = true`. The `attr-defined` error code MUST be suppressed only via per-file `[[tool.mypy.overrides]]` blocks targeting specific modules with known tech debt (e.g., `bot/bot.py`), NOT via a project-wide `disable_error_code`. Per-file overrides SHOULD NOT suppress `type-arg` for any module whose models have been annotated with explicit generic parameters (e.g., `dict[str, Any]`).

(Previously: Per-file overrides did not address `type-arg` suppression; `bot.models.*` had `type-arg` in its override block.)

#### Scenario: Mypy strict mode enabled

- GIVEN `strict = true` is set in `[tool.mypy]`
- WHEN mypy runs against the project
- THEN all strict checks are enforced (warn_return_any, warn_unused_configs, disallow_untyped_defs, etc.)

#### Scenario: attr-defined suppressed per-file only

- GIVEN a `[[tool.mypy.overrides]]` block suppresses `attr-defined` for `bot.bot`
- WHEN mypy encounters `ctx._guild_config` access in `bot/bot.py`
- THEN mypy does not report an `attr-defined` error for that module

#### Scenario: attr-defined still reported in other bot modules

- GIVEN `attr-defined` is suppressed for `bot.bot` (and may also be suppressed for `tests.*` as separate tech debt)
- WHEN mypy encounters an `attr-defined` error in another production `bot.*` module that does not list that code in its override
- THEN the error IS reported

#### Scenario: bot.models has no type-arg suppression

- GIVEN the `[[tool.mypy.overrides]]` block for `bot.models.*` does not include `type-arg` in `disable_error_code`
- WHEN `mypy --strict bot/models/` runs
- THEN zero `type-arg` errors are reported
