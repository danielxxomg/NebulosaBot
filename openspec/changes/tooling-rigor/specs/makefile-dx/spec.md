# Delta for Makefile DX

## MODIFIED Requirements

### Requirement: Makefile provides cov target

The `Makefile` MUST provide a `make cov` target that runs pytest with coverage, displays the coverage report, and enforces a 75% coverage floor via `--cov-fail-under=75`.

(Previously: `make cov` showed coverage but did not enforce a floor)

#### Scenario: make cov shows coverage

- GIVEN the developer runs `make cov`
- WHEN the target executes
- THEN pytest runs with `--cov=bot` and displays a coverage summary

#### Scenario: make cov enforces 75% gate

- GIVEN the developer runs `make cov`
- WHEN total `bot/` coverage is below 75%
- THEN the target fails with a coverage shortfall message
