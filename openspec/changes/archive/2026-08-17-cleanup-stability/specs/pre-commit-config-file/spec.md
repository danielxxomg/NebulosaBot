# Delta for pre-commit-config-file

## MODIFIED Requirements

### Requirement: Hook list includes ruff check and ruff format

The pre-commit config MUST define `ruff check` and `ruff format --check` as separate hooks in that order. Each hook MUST use `files: "^(bot/|tests/)"` instead of a hardcoded file allowlist, and the Ruff hook revision MUST be pinned to `0.15.20` so local and CI checks use the same formatter.

#### Scenario: Ruff check runs first

- GIVEN `.pre-commit-config.yaml` lists `ruff check` before `ruff format`
- WHEN pre-commit executes
- THEN `ruff check` runs before `ruff format --check`

#### Scenario: Hooks scope to bot and tests directories

- GIVEN ruff hooks use `files: "^(bot/|tests/)"`
- WHEN a developer commits `bot/cogs/tickets.py`
- THEN both Ruff hooks run against that file

#### Scenario: Non-target files skipped

- GIVEN ruff hooks use `files: "^(bot/|tests/)"`
- WHEN a developer commits `README.md`
- THEN Ruff hooks are skipped for that commit

#### Scenario: Ruff revision is reproducible

- GIVEN the hook revision is pinned to `0.15.20`
- WHEN pre-commit creates its environment
- THEN it installs the pinned Ruff release rather than a floating version

## ADDED Requirements

### Requirement: Full QA gate is executable

The configured hooks MUST support `pre-commit run --all-files` as a blocking repository gate. That invocation MUST evaluate every `bot/` and `tests/` file through the configured Ruff, mypy, Bandit, and GGA hooks and MUST return non-zero when any required hook fails.

#### Scenario: Baseline all-files run passes

- GIVEN the cleanup baseline has no blocking findings
- WHEN `pre-commit run --all-files` executes
- THEN all configured hooks complete successfully

#### Scenario: A hook failure blocks the gate

- GIVEN a targeted source or test file introduces a blocking finding
- WHEN `pre-commit run --all-files` executes
- THEN the command exits non-zero and identifies the failing hook
