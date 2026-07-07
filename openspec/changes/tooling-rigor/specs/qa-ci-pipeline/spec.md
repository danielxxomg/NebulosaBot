# Delta for CI Pipeline

## MODIFIED Requirements

### Requirement: Matrix CI on push and pull request

The CI pipeline MUST run on every push to any branch and on every pull request targeting `master`. The matrix MUST include Python 3.11, 3.12, 3.13, and 3.14.

(Previously: matrix included 3.11, 3.12, and 3.14 — missing 3.13 which is the production runtime)

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

### Requirement: Coverage gate ratchet

The CI MUST enforce a coverage floor of 75%. The gate value is read from `pyproject.toml` `addopts`.

(Previously: gate was 70% after PR3)

#### Scenario: Coverage gate at 75%

- GIVEN `pyproject.toml` `addopts` sets `--cov-fail-under=75`
- WHEN CI runs on any push or PR
- THEN coverage at or above 75% passes; below 75% fails
