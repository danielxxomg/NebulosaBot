# Delta for pre-commit-config-file

## MODIFIED Requirements

### Requirement: Hook list includes ruff check and ruff format

`prek.toml` MUST define `ruff check` (`--fix`) and `ruff format` (`--check`) as separate hooks in that order. Each hook's `files` MUST be `^(bot/|tests/)`. Ruff pinned `0.15.20` via dev group (prek uses `language = "system"`).

(Previously: `.pre-commit-config.yaml` with `rev: v0.15.20` on ruff-pre-commit repo)

#### Scenario: Hooks scope to bot and tests, skip others

- GIVEN ruff hooks use `files: "^(bot/|tests/)"`
- WHEN a developer commits `bot/cogs/tickets.py` or `README.md`
- THEN both ruff hooks run for `bot/` files and are skipped for `README.md`

### Requirement: Full QA gate is executable

Hooks MUST support `prek run --all-files` as a blocking gate over `bot/` and `tests/`, returning non-zero on any failure.

(Previously: `pre-commit run --all-files` over ruff/mypy/bandit/GGA)

#### Scenario: Baseline passes; failure blocks

- GIVEN baseline has no blocking findings, or a file introduces one
- WHEN `prek run --all-files` executes
- THEN it passes on a clean baseline and exits non-zero on a finding

## REMOVED Requirements

### Requirement: Hook list includes mypy

(Reason: ty replaces mypy)
(Migration: prek local hook `entry: uv run ty check bot/ tests/`, `language: "system"`)

### Requirement: Hook list includes bandit

(Reason: bandit deleted; Ruff S is strictly broader)
(Migration: ruff `S` select already enforced; no separate security hook)

## ADDED Requirements

### Requirement: prek.toml is the single source of truth

A `prek.toml` in repo root MUST be the hook source of truth. Legacy `.pre-commit-config.yaml` MUST be deleted. Config MUST use `[[repos]]` TOML with `repo = "builtin"` and `repo = "local"`.

#### Scenario: prek.toml exists and YAML is deleted

- GIVEN migration is complete
- WHEN the repo root is inspected
- THEN `prek.toml` exists and `.pre-commit-config.yaml` does not

### Requirement: Built-in hooks from prek

`prek.toml` MUST include `repo = "builtin"` with `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`. Archive/markdown/json/css/js/ts exclusions preserved.

#### Scenario: Builtin hooks run without remote fetch

- GIVEN `prek.toml` lists the four builtin hooks
- WHEN `prek run --all-files` executes
- THEN all four checks run without fetching a remote repo

### Requirement: ty local hook

`prek.toml` MUST include a local hook `entry: uv run ty check bot/ tests/`, `language: "system"`, `stages = ["pre-commit"]`, after ruff.

#### Scenario: ty runs after ruff

- GIVEN ty hook is listed after ruff hooks
- WHEN prek executes on commit
- THEN ty runs only after ruff passes

#### Scenario: ty error blocks commit

- GIVEN a staged file introduces a ty error diagnostic
- WHEN `git commit` runs
- THEN the ty hook fails and the commit is aborted

### Requirement: GGA local hook preserved

`prek.toml` MUST include GGA as `repo = "local"`, `entry: bash .gga`, `language: "system"`, `always_run: true`, `pass_filenames: false`, `stages = ["pre-commit"]`.

#### Scenario: GGA runs after ruff and ty, failure blocks

- GIVEN GGA is configured as a local hook
- WHEN the developer commits staged files
- THEN `.gga` executes after ruff and ty, and a non-zero exit aborts the commit

### Requirement: Pre-push stage runs uv check and tach

`prek.toml` MUST include pre-push hooks: `uv check`, `tach check`, `tach check-external`, with `stages = ["pre-push"]`. Tests MUST NOT run per-commit.

#### Scenario: Pre-push runs uv check and tach

- GIVEN pre-push hooks run `uv check`, `tach check`, `tach check-external`
- WHEN `git push` runs
- THEN uv validates the environment and module boundaries are enforced

#### Scenario: Tests not run per-commit

- GIVEN no pytest hook exists in pre-commit stage
- WHEN the developer commits
- THEN the test suite is not invoked

### Requirement: Hook priorities and ordering

`prek.toml` MAY define `[priorities]`. Effective order: builtin → ruff check → ruff format → ty → GGA (pre-commit); uv check → tach check → tach check-external (pre-push).

#### Scenario: Hooks execute in priority order

- GIVEN `prek.toml` defines priorities or relies on list order
- WHEN prek runs the pre-commit stage
- THEN hooks execute in the specified order
