# CI Workflow File Specification

## Purpose

Define the `.github/workflows/ci.yml` GitHub Actions workflow file that enforces the full QA pipeline on push and pull request, with a weekly scheduled dependency audit.

## Requirements

### Requirement: Workflow triggers on push and PR

The CI workflow file MUST trigger on `push` (any branch) and `pull_request` (targeting `master`). It MUST also trigger on a weekly `schedule` cron for dependency auditing.

#### Scenario: Push event triggers workflow

- GIVEN `.github/workflows/ci.yml` exists with `on: push`
- WHEN a commit is pushed to any branch
- THEN the workflow executes

#### Scenario: PR event triggers workflow

- GIVEN the workflow has `on: pull_request` targeting `master`
- WHEN a pull request is opened or updated against `master`
- THEN the workflow executes

#### Scenario: Weekly schedule triggers audit

- GIVEN the workflow has `on: schedule` with a weekly cron
- WHEN the scheduled time arrives
- THEN the workflow executes including `pip-audit`

### Requirement: Matrix with Python 3.11, 3.12, 3.14

The workflow MUST define a strategy matrix with Python versions 3.11, 3.12, and 3.14. Fail-fast MUST be disabled.

#### Scenario: Three Python versions in matrix

- GIVEN the matrix is defined with `[3.11, 3.12, 3.14]`
- WHEN the workflow runs
- THEN three parallel jobs are created, one per Python version

#### Scenario: One failure does not cancel others

- GIVEN fail-fast is disabled
- WHEN the Python 3.11 job fails
- THEN the Python 3.12 and 3.14 jobs continue to completion

### Requirement: PYTHONASYNCIODEBUG=1 in environment

The workflow MUST set `PYTHONASYNCIODEBUG=1` in the job environment for all matrix cells.

#### Scenario: Asyncio debug active in CI

- GIVEN `PYTHONASYNCIODEBUG=1` is set in the workflow env
- WHEN pytest runs in CI
- THEN asyncio debug mode is active and coroutine bugs surface

### Requirement: Dependency caching

The workflow SHOULD cache Python dependencies (e.g., via `actions/cache` or `uv` cache) to reduce job duration.

#### Scenario: Cache restores dependencies

- GIVEN a previous CI run cached the dependency set
- WHEN a new CI run starts with identical `uv.lock`
- THEN the cached dependencies are restored instead of re-downloading
