# CI Pipeline Specification

## Purpose

Enforce linting, type checking, security scanning, coverage gates, and dependency auditing on every push and pull request via GitHub Actions, with a weekly scheduled audit for transitive dependency vulnerabilities.

## Requirements

### Requirement: Matrix CI on push and pull request

The CI pipeline MUST run on every push to any branch and on every pull request targeting `master`. The matrix MUST include Python 3.11, 3.12, 3.13, and 3.14.

#### Scenario: Push triggers full matrix

- GIVEN a developer pushes a commit to any branch
- WHEN GitHub Actions receives the push event
- THEN jobs run for Python 3.11, 3.12, 3.13, and 3.14 in parallel

#### Scenario: PR triggers full matrix

- GIVEN a pull request is opened targeting `master`
- WHEN GitHub Actions receives the PR event
- THEN jobs run for Python 3.11, 3.12, 3.13, and 3.14 in parallel

#### Scenario: Fail-fast disabled

- GIVEN the matrix is running
- WHEN one Python version fails
- THEN the remaining matrix cells continue to completion

### Requirement: Each job runs lint, type, security, and coverage

Each matrix cell MUST execute ruff check, ruff format --check, mypy, bandit, and pytest with coverage in a single job.

#### Scenario: Lint failure blocks CI

- GIVEN a push introduces a ruff violation
- WHEN CI runs on that push
- THEN the job fails at the ruff check step and reports the violation

#### Scenario: Type error blocks CI

- GIVEN a push introduces a mypy error
- WHEN CI runs on that push
- THEN the job fails at the mypy step and reports the error location

#### Scenario: Security issue blocks CI

- GIVEN a push introduces a bandit finding at medium severity or above
- WHEN CI runs on that push
- THEN the job fails at the bandit step

#### Scenario: Coverage below gate blocks CI

- GIVEN total `bot/` coverage is below the current gate threshold
- WHEN pytest runs with `--cov-fail-under`
- THEN the job fails with a coverage shortfall message

### Requirement: Coverage gate ratchet

The CI MUST enforce a coverage floor of 75%. The gate value is read from `pyproject.toml` `addopts`.

#### Scenario: Coverage gate at 75%

- GIVEN `pyproject.toml` `addopts` sets `--cov-fail-under=75`
- WHEN CI runs on any push or PR
- THEN coverage at or above 75% passes; below 75% fails

### Requirement: asyncio debug enabled in CI

The CI MUST set `PYTHONASYNCIODEBUG=1` in the job environment so latent coroutine bugs surface as test failures or warnings.

#### Scenario: Coroutine warning surfaces

- GIVEN a code path contains a forgotten `await`
- WHEN tests run with `PYTHONASYNCIODEBUG=1`
- THEN the warning is surfaced (either as a test failure if warnings are errors, or logged for review)

### Requirement: pip-audit on push and weekly schedule

The CI MUST run `pip-audit` on every push/PR AND on a weekly cron schedule to catch transitive dependency vulnerabilities.

#### Scenario: Push triggers pip-audit

- GIVEN a developer pushes a commit
- WHEN CI runs
- THEN `pip-audit` scans all installed dependencies and fails on known vulnerabilities

#### Scenario: Weekly scheduled audit

- GIVEN a week has passed since the last scheduled run
- WHEN the cron trigger fires
- THEN `pip-audit` runs against the latest `uv.lock` and reports findings

### Requirement: Dependency caching

The CI SHOULD cache Python dependencies between runs to reduce job duration.

#### Scenario: Cache hit on repeated run

- GIVEN dependencies have not changed since the last CI run
- WHEN a new push triggers CI
- THEN the cached dependencies are restored and the install step is skipped or accelerated
