# Delta for ci-workflow-file

## ADDED Requirements

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
