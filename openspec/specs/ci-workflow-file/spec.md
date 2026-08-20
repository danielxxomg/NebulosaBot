# CI Workflow File Specification

## Purpose

Define the `.github/workflows/ci.yml` GitHub Actions workflow file that enforces the full QA pipeline on push and pull request, with a weekly scheduled dependency audit, a blocking `workflow-security` (zizmor) gate, and minimal permissions.

## Requirements

### Requirement: Workflow triggers on push and PR

ci.yml MUST trigger on `push` (any branch), `pull_request` (targeting `master`), and weekly `schedule` cron (for `uv audit`). `concurrency.cancel-in-progress` MUST be true.

#### Scenario: Push event triggers workflow

- GIVEN `.github/workflows/ci.yml` exists with `on: push`
- WHEN a commit is pushed to any branch
- THEN the workflow executes

#### Scenario: PR event triggers workflow

- GIVEN the workflow has `on: pull_request` targeting `master`
- WHEN a pull request is opened or updated against `master`
- THEN the workflow executes

#### Scenario: Weekly schedule triggers audit

- GIVEN the workflow has `on: schedule` with weekly cron
- WHEN the scheduled time arrives
- THEN the workflow runs `uv audit`

### Requirement: Matrix with Python 3.11–3.14

The tests job MUST define a matrix with `["3.11", "3.12", "3.13", "3.14"]` and `fail-fast: false`.

#### Scenario: One failure does not cancel others

- GIVEN fail-fast is disabled
- WHEN the Python 3.11 test job fails
- THEN 3.12, 3.13, 3.14 jobs continue

### Requirement: Coverage gate enforced

The tests job MUST enforce `--cov-fail-under=75` (matching pyproject `addopts`). Coverage artifact upload MUST run on Python 3.12.

#### Scenario: Coverage gate blocks CI

- GIVEN `--cov-fail-under=75` is passed to pytest
- WHEN total `bot/` coverage is below 75%
- THEN the tests job fails

### Requirement: PYTHONASYNCIODEBUG=1 in environment

The tests job MUST set `PYTHONASYNCIODEBUG=1` for all matrix cells.

#### Scenario: Asyncio debug active in CI

- GIVEN `PYTHONASYNCIODEBUG=1` is set
- WHEN pytest runs
- THEN asyncio debug mode is active

### Requirement: setup-uv action SHA-pinned replaces setup-python

The workflow MUST use `astral-sh/setup-uv@<40-char-sha>` (SHA-pinned). MUST NOT use `actions/setup-python` or manual `actions/cache`. Dependencies installed via `uv sync --locked` (not `pip install uv && uv sync --extra dev`).

#### Scenario: setup-uv installs uv

- GIVEN quality and tests jobs use `astral-sh/setup-uv@<sha>`
- WHEN the job starts
- THEN uv is available without a `pip install uv` step

#### Scenario: uv sync uses lock

- GIVEN dependencies installed via `uv sync --locked`
- WHEN the lockfile is current
- THEN `uv sync --locked` succeeds

### Requirement: Three-job structure (quality, tests, workflow-security)

ci.yml MUST define three jobs: (1) `quality` — `uv sync --locked`, `ruff check`, `ruff format --check`, `uv check`, `tach check`, `tach check-external`, `uv audit`; (2) `tests` — matrix pytest `--cov-fail-under=75`; (3) `workflow-security` — zizmor blocking.

#### Scenario: Quality job runs all static gates

- GIVEN the quality job is defined
- WHEN it runs
- THEN ruff, uv check, tach check, tach check-external, and uv audit each block on failure

#### Scenario: Workflow-security job is blocking

- GIVEN the workflow-security job runs zizmor
- WHEN zizmor reports findings
- THEN the job fails

### Requirement: Minimal GitHub permissions

ci.yml MUST declare `permissions: contents: read` top-level. Jobs MAY elevate only needed scopes (e.g., `security-events: write` for SARIF). No `permissions: write-all`.

#### Scenario: Top-level read-only permissions

- GIVEN ci.yml sets `permissions: contents: read`
- WHEN a job without explicit permissions runs
- THEN it inherits read-only contents

### Requirement: pip-audit-weekly job removed

The `pip-audit-weekly` scheduled job MUST be deleted. Auditing handled by `uv audit` in the quality job and weekly schedule.

#### Scenario: pip-audit-weekly absent

- GIVEN migration is complete
- WHEN ci.yml is inspected
- THEN no `pip-audit-weekly` job exists
