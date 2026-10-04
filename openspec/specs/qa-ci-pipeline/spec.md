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

Each matrix cell MUST execute ruff check, ruff format --check, ty check, and pytest with coverage in a single job.

#### Scenario: Lint failure blocks CI

- GIVEN a push introduces a ruff violation
- WHEN CI runs on that push
- THEN the job fails at the ruff check step and reports the violation

#### Scenario: Type error blocks CI

- GIVEN a push introduces a ty error
- WHEN CI runs on that push
- THEN the job fails at the ty step and reports the error location

#### Scenario: Coverage below gate blocks CI

- GIVEN total `bot/` coverage is below the current gate threshold (80.5%)
- WHEN pytest runs with `--cov-fail-under`
- THEN the job fails with a coverage shortfall message

### Requirement: Coverage gate ratchet

The CI MUST enforce a coverage floor of 80.5%. The gate value is read from `pyproject.toml` `addopts`.

#### Scenario: Coverage gate at 80.5%

- GIVEN `pyproject.toml` `addopts` sets `--cov-fail-under=80.5`
- WHEN CI runs on any push or PR
- THEN coverage at or above 80.5% passes; below 80.5% fails

### Requirement: asyncio debug enabled in CI

The CI MUST set `PYTHONASYNCIODEBUG=1` in the job environment so latent coroutine bugs surface as test failures or warnings.

#### Scenario: Coroutine warning surfaces

- GIVEN a code path contains a forgotten `await`
- WHEN tests run with `PYTHONASYNCIODEBUG=1`
- THEN the warning is surfaced (either as a test failure if warnings are errors, or logged for review)

### Requirement: uv audit on push and weekly schedule

The CI MUST run `uv audit` on every push/PR to catch dependency vulnerabilities.

#### Scenario: Push triggers uv audit

- GIVEN a developer pushes a commit
- WHEN CI runs
- THEN `uv audit` scans all installed dependencies and fails on known vulnerabilities

#### Scenario: Weekly scheduled audit

- GIVEN a week has passed since the last scheduled run
- WHEN the cron trigger fires
- THEN `uv audit` runs and reports findings

### Requirement: Dependency caching

The CI SHOULD cache Python dependencies between runs to reduce job duration.

#### Scenario: Cache hit on repeated run

- GIVEN dependencies have not changed since the last CI run
- WHEN a new push triggers CI
- THEN the cached dependencies are restored and the install step is skipped or accelerated

<!-- BEGIN DELTA: cleanup-stability (qa-ci-pipeline) -->
<!-- Delta: cleanup-stability — Hygiene & Stability — blocking gate: `ty check bot tests`, `ruff`, coverage 80.5% -->

### Requirement: Each job runs lint, type, and coverage

Each matrix cell MUST execute `ruff check bot tests`, `ruff format --check bot tests`, `ty check bot tests`, and `pytest --cov=bot --cov-fail-under=80.5 -q` in a blocking job.

#### Scenario: Lint failure blocks CI

- GIVEN a push introduces a Ruff violation anywhere in `bot/` or `tests/`
- WHEN CI runs on that push
- THEN the full-scope Ruff step fails and reports the violation

#### Scenario: Type error blocks CI

- GIVEN a push introduces a ty error in `bot/` or `tests/`
- WHEN CI runs `ty check bot tests` on that push
- THEN the ty step fails and reports the error location

#### Scenario: Coverage below gate blocks CI

- GIVEN total `bot/` coverage is below 80.5%
- WHEN pytest runs with `--cov-fail-under=80.5`
- THEN the job fails with a coverage shortfall

#### Scenario: Current baseline suite remains accepted

- GIVEN the audited baseline suite contains 3,202 passing tests and 19 skips
- WHEN the full pytest gate runs
- THEN the suite passes and coverage is at least 80.5%

<!-- END DELTA: cleanup-stability (qa-ci-pipeline) -->

<!-- BEGIN DELTA: ops-zero-lite (qa-ci-pipeline) -->
## ADDED Requirements

### Requirement: Daily Supabase dump cron via pooler

CI MUST add `.github/workflows/backup.yml` running daily via cron (`0 2 * * *` UTC) that dumps the Supabase DB through the session pooler (port 5432, `SUPABASE_DB_URL` pooler form), uploads artifact with 7-day retention (`retention-days: 7`), and fails visibly on dump error. Workflow MUST use SHA-pinned actions, `uv`/`pg_dump` available on runner, and MUST NOT log `SUPABASE_DB_URL`/`SENTRY_DSN` secrets. Coverage gate remains `--cov-fail-under=80.5` (3202 tests, ~83.4% actual; margin holds — slices MUST keep cov ≥80.5%).

#### Scenario: Cron file exists and triggers daily

- GIVEN `.github/workflows/backup.yml` with `on.schedule.cron` and `on.workflow_dispatch`
- WHEN workflow is parsed
- THEN cron is `0 2 * * *` and manual dispatch is allowed

#### Scenario: Artifact retention 7 days

- GIVEN backup job uploads via `actions/upload-artifact`
- WHEN inspected
- THEN `retention-days` is 7

#### Scenario: Failure surfaces not silent

- GIVEN `pg_dump` exits non-zero
- WHEN job runs
- THEN step fails (no `continue-on-error: true`) and run is marked failed

#### Scenario: Coverage headroom preserved

- GIVEN S0+S1 slices are applied sequentially
- WHEN `uv run pytest --cov-fail-under=80.5` runs (≥3202 passed)
- THEN cov stays ≥80.5%

<!-- END DELTA: ops-zero-lite (qa-ci-pipeline) -->
