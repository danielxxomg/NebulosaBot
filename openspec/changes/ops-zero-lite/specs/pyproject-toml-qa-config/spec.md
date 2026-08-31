# Delta for pyproject-toml-qa-config

## ADDED Requirements

### Requirement: Vulture dead-code from advisory to blocking

Vulture MUST flip from advisory to blocking in `.github/workflows/code-quality.yml`: remove `continue-on-error: true` from the `vulture — dead code report` step (config-only clean per #4700 — ImageService deleted, advisory-clean at S5a `c641...`). Command MUST be `vulture bot/ --min-confidence 80`. Zero findings MUST be the gate; any new dead code at confidence ≥80 fails CI.

#### Scenario: Advisory flag removed

- GIVEN `.github/workflows/code-quality.yml` is parsed
- WHEN locating the vulture step
- THEN `continue-on-error` is absent/false (blocking)

#### Scenario: Vulture reports zero at 80

- GIVEN `vulture bot/ --min-confidence 80` runs on current tree
- WHEN executed
- THEN exit 0 with zero findings

#### Scenario: New dead code blocks PR

- GIVEN a new unused function/class is added to `bot/`
- WHEN vulture runs in CI at 80 confidence
- THEN step fails and PR is blocked
