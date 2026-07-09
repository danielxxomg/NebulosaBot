# Economy Commands Specification

## Purpose

Define the hybrid commands that expose the economy system to Discord users.

## Requirements

### Requirement: /rank command

The system MUST provide a hybrid `/rank [member]` command that returns the rank card image for the invoker or the specified member.

#### Scenario: Self rank

- GIVEN member A invokes `/rank` without arguments
- WHEN the command executes
- THEN a rank card image for member A is returned

#### Scenario: Target rank

- GIVEN member A invokes `/rank @memberB`
- WHEN the command executes
- THEN a rank card image for member B is returned

### Requirement: /leaderboard command

The system MUST provide a hybrid `/leaderboard <xp|coins>` command that displays the top 10 members for the selected metric.

#### Scenario: XP leaderboard

- GIVEN members have XP in guild X
- WHEN `/leaderboard xp` is invoked
- THEN an embed lists the top 10 members by XP with ranks 1–10

#### Scenario: Coins leaderboard

- GIVEN members have coins in guild X
- WHEN `/leaderboard coins` is invoked
- THEN an embed lists the top 10 members by coins with ranks 1–10

#### Scenario: Empty leaderboard

- GIVEN no members have XP or coins in guild X
- WHEN `/leaderboard xp` is invoked
- THEN the embed indicates the leaderboard is empty

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

### Requirement: /coins command

The system MUST provide a hybrid `/coins [member]` command that shows the coin balance of the invoker or the specified member.

#### Scenario: Self balance

- GIVEN member A has 250 coins
- WHEN `/coins` is invoked by member A
- THEN the reply shows 250 coins

#### Scenario: Target balance

- GIVEN member B has 1200 coins
- WHEN `/coins @memberB` is invoked by member A
- THEN the reply shows 1200 coins
