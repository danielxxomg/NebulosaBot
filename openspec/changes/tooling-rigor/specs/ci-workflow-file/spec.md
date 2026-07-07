# Delta for CI Workflow File

## MODIFIED Requirements

### Requirement: Matrix with Python 3.11, 3.12, 3.14

The workflow MUST define a strategy matrix with Python versions 3.11, 3.12, 3.13, and 3.14. Fail-fast MUST be disabled.

(Previously: matrix included 3.11, 3.12, 3.14 — missing 3.13)

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

(Previously: no explicit coverage gate in workflow spec — relied on pyproject.toml addopts only)

#### Scenario: Coverage gate blocks CI

- GIVEN `--cov-fail-under=75` is passed to pytest in the workflow
- WHEN total `bot/` coverage is below 75%
- THEN the job fails with a coverage shortfall message
