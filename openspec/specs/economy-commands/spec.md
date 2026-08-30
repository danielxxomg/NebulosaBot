# Economy Commands Specification

## Purpose

Define the slash-only commands that expose the economy system to Discord users. Bot core is slash-only (`get_prefix -> []`); no prefix/hybrid path is invocable.

## Requirements

### Requirement: /rank command

The system MUST provide a slash-only `/rank [member]` command via `@app_commands.command()` (MUST NOT use `hybrid_command`/`hybrid_group`) that returns the rank card image for the invoker or the specified member. Prefix invocations MUST be inert because `get_prefix` resolves to `[]` (`bot-core` truth). User-facing embeds and errors MUST be resolved via `t()`.

(Previously: hybrid `/rank` via `hybrid_command`)

#### Scenario: Self rank

- GIVEN member A invokes `/rank` without arguments via slash
- WHEN the command executes
- THEN a rank card image for member A is returned

#### Scenario: Target rank

- GIVEN member A invokes `/rank @memberB` via slash
- WHEN the command executes
- THEN a rank card image for member B is returned

#### Scenario: Prefix invocation inert

- GIVEN a user sends `nb!rank` or `!rank` as text
- WHEN the message is processed
- THEN no command is invoked

### Requirement: /leaderboard command

The system MUST provide a slash-only `/leaderboard <xp|coins>` command via `@app_commands.command()` that displays the top 10 members for the selected metric. Prefix invocations MUST be inert. User-facing strings MUST use `t()`.

(Previously: hybrid `/leaderboard`)

#### Scenario: XP leaderboard

- GIVEN members have XP in guild X
- WHEN `/leaderboard xp` is invoked via slash
- THEN an embed lists the top 10 members by XP with ranks 1-10

#### Scenario: Coins leaderboard

- GIVEN members have coins in guild X
- WHEN `/leaderboard coins` is invoked via slash
- THEN an embed lists the top 10 members by coins with ranks 1-10

#### Scenario: Empty leaderboard

- GIVEN no members have XP or coins in guild X
- WHEN `/leaderboard xp` is invoked via slash
- THEN the embed indicates the leaderboard is empty via `t()`

### Requirement: /daily command

The system MUST provide a slash-only `/daily` command via `@app_commands.command()` that claims the daily reward if the cooldown has elapsed. When the cooldown has NOT elapsed, the cooldown embed MUST include the exact remaining time formatted as `Xh Ym` using a `{remaining}` placeholder in the i18n key `stellar.daily.cooldown_description` resolved via `t()`.

(Previously: hybrid `/daily`)

#### Scenario: Successful daily claim

- GIVEN member A is eligible for daily
- WHEN `/daily` is invoked via slash
- THEN coins are awarded with the streak bonus and the embed shows the new streak and amount via `t()`

#### Scenario: Daily on cooldown with exact time

- GIVEN member A claimed daily 2 hours ago (cooldown is 24h)
- WHEN `/daily` is invoked via slash
- THEN the command replies ephemerally with the exact remaining time (e.g., "22h 0m") via `t()` and awards no coins

#### Scenario: Daily on cooldown near expiry

- GIVEN member A claimed daily 23h 50m ago
- WHEN `/daily` is invoked via slash
- THEN the cooldown embed shows "0h 10m" via `t()`

### Requirement: /coins command

The system MUST provide a slash-only `/coins [member]` command via `@app_commands.command()` that shows the coin balance of the invoker or the specified member. Prefix invocations MUST be inert. Balance displays MUST use `t()`.

(Previously: hybrid `/coins`)

#### Scenario: Self balance

- GIVEN member A has 250 coins
- WHEN `/coins` is invoked via slash by member A
- THEN the reply shows 250 coins via `t()`

#### Scenario: Target balance

- GIVEN member B has 1200 coins
- WHEN `/coins @memberB` is invoked via slash by member A
- THEN the reply shows 1200 coins via `t()`
