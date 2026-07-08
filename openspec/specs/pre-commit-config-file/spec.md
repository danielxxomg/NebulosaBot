# Pre-commit Config File Specification

## Purpose

Define `.pre-commit-config.yaml` as the single source of truth for pre-commit hooks, listing ruff, mypy, bandit, and the GGA shell hook in deterministic execution order.

## Requirements

### Requirement: Hook list includes ruff check and ruff format

The pre-commit config MUST define `ruff check` and `ruff format --check` as separate hooks, running in that order. Each hook's `files` pattern MUST be `^(bot/|tests/)` instead of a hardcoded file allowlist.

#### Scenario: Ruff check runs first

- GIVEN `.pre-commit-config.yaml` lists `ruff check` before `ruff format`
- WHEN pre-commit executes
- THEN `ruff check` runs before `ruff format --check`

#### Scenario: Hooks scope to bot and tests directories

- GIVEN ruff hooks use `files: "^(bot/|tests/)"`
- WHEN a developer commits a change to `bot/cogs/tickets.py`
- THEN ruff check and ruff format run against that file

#### Scenario: Non-target files skipped

- GIVEN ruff hooks use `files: "^(bot/|tests/)"`
- WHEN a developer commits a change to `README.md`
- THEN ruff hooks are skipped for that commit

### Requirement: Hook list includes mypy

The pre-commit config MUST define a mypy hook that runs after ruff hooks. The mypy hook's `files` pattern MUST be `^(bot/|tests/)`.

#### Scenario: Mypy runs after ruff

- GIVEN mypy is listed after ruff in the config
- WHEN pre-commit executes
- THEN mypy runs only after ruff check and ruff format pass

#### Scenario: Mypy scopes to bot and tests

- GIVEN mypy hook uses `files: "^(bot/|tests/)"`
- WHEN a developer commits a change to `bot/services/guild_service.py`
- THEN mypy type-checks that file

### Requirement: Hook list includes bandit

The pre-commit config MUST define a bandit hook that runs after mypy.

#### Scenario: Bandit runs after mypy

- GIVEN bandit is listed after mypy in the config
- WHEN pre-commit executes
- THEN bandit runs only after mypy passes

### Requirement: GGA shell hook as script entry

The pre-commit config MUST include the existing `.gga` hook as a `language: script` entry, running last in the hook chain.

#### Scenario: GGA runs last

- GIVEN `.gga` is configured as the final hook with `language: script`
- WHEN pre-commit executes
- THEN `.gga` runs after ruff, mypy, and bandit all pass

#### Scenario: GGA failure blocks commit

- GIVEN `.gga` exits with a non-zero status
- WHEN pre-commit executes
- THEN the commit is aborted and the GGA output is displayed

### Requirement: Deterministic hook ordering

The hooks MUST execute in the order: ruff check → ruff format → mypy → bandit → GGA. This order is specified by the file's hook list sequence.

#### Scenario: Hooks execute in listed order

- GIVEN the pre-commit config defines hooks in the specified order
- WHEN a developer commits
- THEN hooks execute sequentially in that exact order
