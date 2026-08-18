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

### Requirement: Matrix with Python 3.11, 3.12, 3.13, 3.14

The workflow MUST define a strategy matrix with Python versions 3.11, 3.12, 3.13, and 3.14. Fail-fast MUST be disabled.

#### Scenario: Four Python versions in matrix

- GIVEN the matrix is defined with `[3.11, 3.12, 3.13, 3.14]`
- WHEN the workflow runs
- THEN four parallel jobs are created, one per Python version

#### Scenario: One failure does not cancel others

- GIVEN fail-fast is disabled
- WHEN the Python 3.11 job fails
- THEN the Python 3.12, 3.13, and 3.14 jobs continue to completion

### Requirement: Coverage gate enforced in workflow

The workflow MUST enforce a coverage floor of 75% via `--cov-fail-under=75` passed to pytest. The gate value MUST match `pyproject.toml` `addopts`.

#### Scenario: Coverage gate blocks CI

- GIVEN `--cov-fail-under=75` is passed to pytest in the workflow
- WHEN total `bot/` coverage is below 75%
- THEN the job fails with a coverage shortfall message

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

<!-- BEGIN DELTA: cleanup-stability (ci-workflow-file) -->
<!-- Delta: cleanup-stability — Hygiene & Stability (S1 L3) — Deferred to S2: ci-workflow-file delta proposed `mypy bot tests` full scope but S1 ships `mypy bot/` only (28 tests.* errors deferred). This delta is preserved as the S2 target; archive reports S1 as PASS_WITH_WARNINGS with S2 deferral. Live alignment deferred to S2 `refactor-ticket-domain`. -->

### Requirement: Blocking QA job covers bot and tests

The blocking job in `.github/workflows/ci.yml` MUST run QA against the complete `bot/` and `tests/` scope rather than curated file lists. It MUST run `ruff check bot tests`, `ruff format --check bot tests`, `mypy bot tests`, the configured medium-or-higher Bandit scan for `bot/`, and `pytest --cov=bot --cov-fail-under=75`. A failure in any gate MUST fail the job. Files under `scripts/` MAY remain outside this blocking scope unless explicitly added.

#### Scenario: Full source scope is checked

- GIVEN a push or pull request reaches the blocking QA job
- WHEN the job runs its quality steps
- THEN all five commands inspect the required bot/test scope

#### Scenario: Curated-list drift cannot pass

- GIVEN a violation exists in an otherwise omitted `bot/` or `tests/` file
- WHEN the workflow runs
- THEN the corresponding full-scope gate reports it and the job fails

#### Scenario: Baseline verification remains green

- GIVEN revision `f83e767` and its dependencies are used
- WHEN the blocking job runs
- THEN Ruff, mypy, Bandit, and pytest meet their configured gates

*S1 note: `mypy bot tests` is the S2 target; S1 ships `mypy bot/` with `tests.*` deferred (28 errors). The S1 pipeline is PASS_WITH_WARNINGS pending S2. See `verify-report.md` CRITICAL CI-1 and S2 follow-up.*

<!-- END DELTA: cleanup-stability (ci-workflow-file) -->
