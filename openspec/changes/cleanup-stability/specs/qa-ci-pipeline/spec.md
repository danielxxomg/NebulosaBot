# Delta for qa-ci-pipeline

## MODIFIED Requirements

### Requirement: Each job runs lint, type, security, and coverage

Each matrix cell MUST execute `ruff check bot tests`, `ruff format --check bot tests`, `mypy bot` (blocking; `mypy bot tests` deferred to S2 with 28 inventoried tests.* errors — S1 gates `bot/` only), `bandit -r bot -c pyproject.toml --severity-level medium`, and `pytest --cov=bot --cov-fail-under=75 -q` in a blocking job. `bot/` scope is fully gated; `tests/` type debt is an explicit S2 deferral documented in proposal/specs.

#### Scenario: Lint failure blocks CI

- GIVEN a push introduces a Ruff violation anywhere in `bot/` or `tests/`
- WHEN CI runs on that push
- THEN the full-scope Ruff step fails and reports the violation

#### Scenario: Type error blocks CI

- GIVEN a push introduces a mypy error in `bot/` (S1 gate; `tests/` debt deferred to S2)
- WHEN CI runs `mypy bot` on that push
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

- GIVEN the audited baseline suite contains 1,814 passing tests and 3 skips (was 1,761 at f83e767; now 1814 after PR1-3)
- WHEN the full pytest gate runs
- THEN the suite passes and coverage is at least 75%
