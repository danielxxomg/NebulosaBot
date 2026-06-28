# Pre-commit Specification

## Purpose

Enforce linting, type checking, security scanning, and code review gates on every `git commit` via the pre-commit framework, integrating the existing GGA shell hook as a first-class step.

## Requirements

### Requirement: Pre-commit runs all QA hooks

The pre-commit framework MUST execute ruff check, ruff format, mypy, bandit, and the GGA shell hook on staged files when a developer runs `git commit`.

#### Scenario: Clean commit passes all hooks

- GIVEN all staged files pass ruff, mypy, bandit, and GGA checks
- WHEN the developer runs `git commit`
- THEN all hooks pass and the commit is created

#### Scenario: Ruff violation blocks commit

- GIVEN a staged file contains a ruff lint violation
- WHEN the developer runs `git commit`
- THEN the ruff check hook fails and the commit is aborted

#### Scenario: Mypy error blocks commit

- GIVEN a staged file introduces a mypy type error
- WHEN the developer runs `git commit`
- THEN the mypy hook fails and the commit is aborted

#### Scenario: Bandit finding blocks commit

- GIVEN a staged file contains a security finding at medium severity or above
- WHEN the developer runs `git commit`
- THEN the bandit hook fails and the commit is aborted

### Requirement: Hook ordering

Pre-commit hooks MUST execute in a deterministic order: ruff check first, then ruff format, then mypy, then bandit, then GGA. Faster hooks run before slower ones.

#### Scenario: Lint fails before type check runs

- GIVEN a staged file has both a ruff violation and a mypy error
- WHEN pre-commit executes
- THEN ruff check fails first and mypy is not executed for that commit attempt

### Requirement: GGA integration as script hook

The existing `.gga` shell hook MUST be wrapped as a `language: script` entry in `.pre-commit-config.yaml` so pre-commit invokes it as part of the hook chain.

#### Scenario: GGA runs on staged files

- GIVEN `.gga` is configured as a script hook
- WHEN the developer commits staged files
- THEN `.gga` executes after ruff, mypy, and bandit complete

### Requirement: SKIP bypasses hooks

Setting the `SKIP` environment variable to a comma-separated list of hook IDs MUST skip those hooks for that commit.

#### Scenario: Skip mypy on WIP commit

- GIVEN the developer sets `SKIP=mypy` before committing
- WHEN the developer runs `git commit`
- THEN mypy is skipped and the remaining hooks still execute

#### Scenario: Skip all hooks

- GIVEN the developer sets `SKIP=ruff-check,ruff-format,mypy,bandit,gga`
- WHEN the developer runs `git commit`
- THEN all hooks are skipped and the commit proceeds
