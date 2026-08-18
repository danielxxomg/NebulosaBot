# Delta for Permission Model

## MODIFIED Requirements

### Requirement: `is_mod` dual-path characterization

The system MUST preserve the existing `is_mod` decorator path and `is_mod_check` inline path without changing permission decisions. Characterization coverage MUST account for 25 `@is_mod()` decorator applications (17 in `tickets.py` and 8 in `sentinel.py`) and every inline `is_mod_check` call, including persistent and ephemeral ticket view callbacks. The behavior MUST remain a single decision point in `bot/utils/checks.py`.

(Previously: characterization counted 23 decorator callers and 21 inline callers.)

#### Scenario: Both hybrid paths remain registered

- GIVEN a command is decorated with `@is_mod()`
- WHEN its checks are inspected
- THEN both prefix and slash predicates are registered

#### Scenario: Inline view checks remain fail-closed

- GIVEN a ticket view callback runs without a guild, role, or valid moderator context
- WHEN `is_mod_check` is evaluated
- THEN it denies without weakening the existing permission behavior

#### Scenario: Caller characterization passes

- GIVEN the 25 decorator applications and all inline call sites are exercised
- WHEN the S3 permission test suite runs
- THEN all existing administrator, moderator, regular-user, and DM outcomes remain unchanged
