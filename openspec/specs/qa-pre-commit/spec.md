# Pre-commit Specification

## Purpose

Enforce linting, type checking, security scanning (via Ruff `S`), and code review gates on every `git commit` via the prek framework, integrating the existing GGA shell hook as a first-class step. Pre-push gates enforce environment and module-boundary checks.

## Requirements

### Requirement: Pre-commit runs all QA hooks

The prek framework MUST execute ruff check, ruff format, ty, and the GGA shell hook on staged files when a developer runs `git commit`. Bandit MUST NOT be a hook (replaced by Ruff `S` rules). mypy MUST NOT be a hook (replaced by ty).

#### Scenario: Clean commit passes all hooks

- GIVEN all staged files pass ruff, ty, and GGA checks
- WHEN the developer runs `git commit`
- THEN all hooks pass and the commit is created

#### Scenario: Ruff violation blocks commit

- GIVEN a staged file contains a ruff lint violation
- WHEN the developer runs `git commit`
- THEN the ruff check hook fails and the commit is aborted

#### Scenario: ty error blocks commit

- GIVEN a staged file introduces a ty error-severity diagnostic
- WHEN the developer runs `git commit`
- THEN the ty hook fails and the commit is aborted

### Requirement: Hook ordering

Prek hooks MUST execute in a deterministic order: ruff check first, then ruff format, then ty, then GGA. Faster hooks run before slower ones. Builtin hygiene hooks (trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files) run before project hooks.

#### Scenario: Lint fails before type check runs

- GIVEN a staged file has both a ruff violation and a ty error
- WHEN prek executes
- THEN ruff check fails first and ty is not executed for that commit attempt

### Requirement: Pre-push gate runs environment and boundary checks

The prek framework MUST run `uv check`, `tach check`, and `tach check-external` on `git push` via pre-push stage hooks. These checks MUST block the push on failure.

#### Scenario: uv check failure blocks push

- GIVEN the environment is inconsistent with the lockfile
- WHEN `git push` runs
- THEN the uv check hook fails and the push is aborted

#### Scenario: tach violation blocks push

- GIVEN a module imports outside its allowed layer
- WHEN `git push` runs
- THEN the tach check hook fails and the push is aborted

#### Scenario: External dependency violation blocks push

- GIVEN a module imports an external package not declared in its dependencies
- WHEN `git push` runs
- THEN tach check-external fails and the push is aborted

### Requirement: SKIP bypasses hooks

Setting the `SKIP` environment variable to a comma-separated list of hook IDs MUST skip those hooks for that commit. Hook IDs MUST match the `id` fields in `prek.toml`.

#### Scenario: Skip ty on WIP commit

- GIVEN the developer sets `SKIP=ty` before committing
- WHEN the developer runs `git commit`
- THEN ty is skipped and the remaining hooks still execute

#### Scenario: Skip all hooks

- GIVEN the developer sets `SKIP=ruff-check,ruff-format,ty,gga`
- WHEN the developer runs `git commit`
- THEN all hooks are skipped and the commit proceeds
