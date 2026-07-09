# Delta for Economy Service

## MODIFIED Requirements

### Requirement: XP gain with cooldown

The system MUST award XP only when the configured per-user per-guild cooldown has elapsed. The cooldown check MUST safely parse `lastXpGain` from ISO datetime string (or `datetime`) before comparison. A shared `_to_datetime` helper MUST be used by both `gain_xp` and `claim_daily`.

(Previously: gain_xp compared raw ISO string with datetime object, causing TypeError on cooldown check)

#### Scenario: XP awarded after cooldown

- GIVEN member A's cooldown has elapsed
- WHEN an XP gain is processed
- THEN total XP increases by `xpPerMessage`

#### Scenario: XP gain blocked during cooldown

- GIVEN member A gained XP less than `xpCooldownSeconds` ago
- WHEN another XP gain is processed
- THEN no XP is awarded and the total is unchanged

#### Scenario: Cooldown is per guild

- GIVEN member A is in guilds X and Y
- WHEN XP is gained in guild X
- THEN XP may still be gained in guild Y

#### Scenario: String-type lastXpGain parsed safely

- GIVEN member A's `lastXpGain` is an ISO datetime string (e.g. `"2025-07-09T12:00:00+00:00"`)
- WHEN `gain_xp` checks the cooldown
- THEN the string is parsed to `datetime` before subtraction
- AND no `TypeError` is raised

#### Scenario: Datetime-type lastXpGain works unchanged

- GIVEN member A's `lastXpGain` is already a `datetime` object
- WHEN `gain_xp` checks the cooldown
- THEN the comparison works without error

#### Scenario: claim_daily uses shared helper

- GIVEN `claim_daily` checks the daily cooldown
- WHEN the cooldown is evaluated
- THEN the shared `_to_datetime` helper is used (same logic as `gain_xp`)
