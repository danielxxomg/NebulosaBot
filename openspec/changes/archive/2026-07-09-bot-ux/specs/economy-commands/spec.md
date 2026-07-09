# Delta for Economy Commands

## MODIFIED Requirements

### Requirement: /daily command

The system MUST provide a hybrid `/daily` command that claims the daily reward if the cooldown has elapsed. When the cooldown has NOT elapsed, the cooldown embed MUST include the exact remaining time formatted as `Xh Ym` using a `{remaining}` placeholder in the i18n key `stellar.daily.cooldown_description`.

(Previously: cooldown embed showed a vague "come back tomorrow!" with no remaining time)

#### Scenario: Successful daily claim

- GIVEN member A is eligible for daily
- WHEN `/daily` is invoked
- THEN coins are awarded with the streak bonus and the embed shows the new streak and amount

#### Scenario: Daily on cooldown with exact time

- GIVEN member A claimed daily 2 hours ago (cooldown is 24h)
- WHEN `/daily` is invoked
- THEN the command replies with the exact remaining time (e.g., "You can claim again in 22h 0m") and awards no coins

#### Scenario: Daily on cooldown near expiry

- GIVEN member A claimed daily 23h 50m ago
- WHEN `/daily` is invoked
- THEN the cooldown embed shows "You can claim again in 0h 10m"
