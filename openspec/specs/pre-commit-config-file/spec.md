# Pre-commit Config File Specification

## Purpose

Define `prek.toml` as the single source of truth for pre-commit hooks, listing builtin hygiene hooks, ruff check/format, ty, the GGA shell hook, and pre-push uv-check/tach gates in deterministic execution order. Legacy `.pre-commit-config.yaml` is deleted.

## Requirements

### Requirement: Hook list includes ruff check and ruff format

`prek.toml` MUST define `ruff check` (`--fix`) and `ruff format` (`--check`) as separate hooks in that order. Each hook's `files` MUST be `^(bot/|tests/)`. Ruff pinned `0.15.20` via dev group (prek uses `language = "system"`).

#### Scenario: Hooks scope to bot and tests, skip others

- GIVEN ruff hooks use `files: "^(bot/|tests/)"`
- WHEN a developer commits `bot/cogs/tickets.py` or `README.md`
- THEN both ruff hooks run for `bot/` files and are skipped for `README.md`

#### Scenario: Ruff check runs before format

- GIVEN `prek.toml` lists `ruff check` before `ruff format`
- WHEN prek executes
- THEN `ruff check` runs before `ruff format --check`

### Requirement: Full QA gate is executable

Hooks MUST support `prek run --all-files` as a blocking gate over `bot/` and `tests/`, returning non-zero on any failure.

#### Scenario: Baseline passes; failure blocks

- GIVEN baseline has no blocking findings, or a file introduces one
- WHEN `prek run --all-files` executes
- THEN it passes on a clean baseline and exits non-zero on a finding

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

### Requirement: Pre-push stage runs uv lock check and tach

`prek.toml` MUST include pre-push hooks: `uv-lock-check` (local id, entry `uv lock --check`), `tach check`, and `tach check-external`, each with `stages = ["pre-push"]`. Tests MUST NOT run per-commit.

#### Scenario: Pre-push runs lock check and tach

- GIVEN pre-push hooks run `uv-lock-check`, `tach check`, `tach check-external`
- WHEN `git push` runs
- THEN lockfile freshness is verified and module boundaries are enforced

#### Scenario: Stale lock blocks push

- GIVEN `pyproject.toml` changed without regenerating `uv.lock`
- WHEN the developer pushes
- THEN `uv-lock-check` fails and the push is aborted

### Requirement: Hook priorities and ordering

`prek.toml` MAY define `[priorities]`. Effective order: builtin → ruff check → ruff format → ty → GGA (pre-commit); uv-lock-check → jscpd-check → tach check → tach check-external (pre-push).

(Previously: the pre-push order referenced `uv check` and had no duplication hook.)

#### Scenario: Hooks execute in priority order

- GIVEN `prek.toml` defines priorities or relies on list order
- WHEN prek runs the pre-push stage
- THEN hooks execute in the specified order (lock check, duplication, tach)

<!-- BEGIN DELTA: cycle-4-debt-zero (pre-commit-config-file) -->
## ADDED Requirements

### Requirement: jscpd-check pre-push hook

`prek.toml` MUST include a local `jscpd-check` hook in the pre-push stage scoped to `^(bot/|tests/)` that invokes the duplication budget checker (see the duplication-budget specification). A push MUST abort on any non-zero checker exit.

#### Scenario: Push blocked above duplication ceiling

- GIVEN duplication exceeds a committed baseline ceiling
- WHEN the developer pushes
- THEN `jscpd-check` exits non-zero and the push is aborted

#### Scenario: Push proceeds within ceiling

- GIVEN duplication is within all ceilings
- WHEN the developer pushes
- THEN `jscpd-check` passes and the push proceeds
<!-- END DELTA: cycle-4-debt-zero (pre-commit-config-file) -->
