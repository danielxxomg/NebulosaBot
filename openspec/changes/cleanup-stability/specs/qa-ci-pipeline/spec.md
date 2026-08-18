# Delta for qa-ci-pipeline

## MODIFIED Requirements

### Requirement: Each job runs lint, type, security, and coverage

Each matrix cell MUST execute `ruff check bot tests`, `ruff format --check bot tests`, `mypy bot tests`, `bandit -r bot -c pyproject.toml --severity-level medium`, and `pytest --cov=bot --cov-fail-under=75 -q` in a blocking job. These commands MUST cover all `bot/` and `tests/` files, not a curated subset.

#### Scenario: Lint failure blocks CI

- GIVEN a push introduces a Ruff violation anywhere in `bot/` or `tests/`
- WHEN CI runs on that push
- THEN the full-scope Ruff step fails and reports the violation

#### Scenario: Type error blocks CI

- GIVEN a push introduces a mypy error in `bot/` or `tests/`
- WHEN CI runs on that push
- THEN the mypy step fails and reports the error location

#### Scenario: Security issue blocks CI

- GIVEN a push introduces a medium-or-higher Bandit finding in `bot/`
- WHEN CI runs on that push
- THEN the Bandit step fails

#### Scenario: Coverage below gate blocks CI

- GIVEN total `bot/` coverage is below 75%
- WHEN pytest runs with `--cov-fail-under=75`
- THEN the job fails with a coverage shortfall

#### Scenario: Current baseline suite remains accepted

- GIVEN the audited baseline suite contains 1,761 passing tests and 3 skips
- WHEN the full pytest gate runs
- THEN the suite passes and coverage is at least 75%
