# Delta for pyproject-toml-qa-config

## MODIFIED Requirements

### Requirement: Mypy configuration present

`pyproject.toml` MUST contain a `[tool.mypy]` section with `strict = true`. Per-file `[[tool.mypy.overrides]]` blocks MUST exist ONLY for modules with known tech debt that cannot be resolved without behavioral changes: `bot.cogs.*` (`untyped-decorator`) and `tests.*`. The override blocks for `bot.core.*`, `bot.listeners.*`, and `bot.bot` MUST NOT be present — those modules SHALL pass strict mypy without suppression. Per-file overrides SHOULD NOT suppress `type-arg` for any module whose models have been annotated with explicit generic parameters (e.g., `dict[str, Any]`).

(Previously: three additional override blocks existed for `bot.core.*`, `bot.listeners.*`, and `bot.bot`; `attr-defined` was suppressed project-wide via per-file overrides)

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
