# Economy Service Specification

## Purpose

Define business rules for guild economy: XP gain, level progression, daily coin claims with streak bonuses, coin balance, and leaderboards.

## Requirements

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

### Requirement: Level calculation

The system MUST compute a member's level from total XP using `levelBaseXp * (levelMultiplier ^ level)`.

#### Scenario: Level threshold

- GIVEN `levelBaseXp` is 100 and `levelMultiplier` is 1.5
- WHEN computing XP needed for level 3
- THEN the threshold equals 337.5 XP

#### Scenario: Level from XP

- GIVEN a member has 400 XP and the configured formula
- WHEN the level is computed
- THEN it is the highest integer whose threshold does not exceed 400 XP

### Requirement: Daily coin claim with streak bonus

The system MUST award daily coins equal to `dailyReward * (1 + 0.10 * min(streak,7))` and reset the streak when more than `dailyCooldownHours` have passed.

#### Scenario: First daily claim

- GIVEN a member has never claimed daily
- WHEN daily is claimed
- THEN `coins` increases by `dailyReward` and `daily_streak` becomes 1

#### Scenario: Consecutive daily claim

- GIVEN a member claimed 20 hours ago with `daily_streak` 3
- WHEN daily is claimed again
- THEN `daily_streak` becomes 4 and coins increase by 140% of `dailyReward`

#### Scenario: Streak bonus cap

- GIVEN `daily_streak` is 7
- WHEN daily is claimed consecutively
- THEN coins increase by 160% of `dailyReward` and streak stays at 7

#### Scenario: Broken streak

- GIVEN a member claimed 48 hours ago with `daily_streak` 5
- WHEN daily is claimed
- THEN `daily_streak` resets to 1 and coins increase by `dailyReward`

#### Scenario: Daily cooldown blocks claim

- GIVEN a member claimed 2 hours ago with `dailyCooldownHours` 24
- WHEN daily is claimed again
- THEN the claim is rejected and no coins are awarded

### Requirement: Coin balance

The system MUST maintain an integer coin balance per member and support incrementing and querying it.

#### Scenario: Award daily coins

- GIVEN a member claims daily successfully
- WHEN coins are credited
- THEN the balance reflects the awarded amount

#### Scenario: Query balance

- GIVEN a member has 500 coins
- WHEN the balance is queried
- THEN the result is 500

### Requirement: Leaderboard queries

The system MUST provide separate leaderboard queries for XP and coins, ordered descending, with optional limit and offset.

#### Scenario: XP leaderboard

- GIVEN 15 members with varying XP in guild X
- WHEN the XP leaderboard is queried with limit 10 and offset 0
- THEN the result contains the top 10 members by XP

#### Scenario: Coins leaderboard

- GIVEN 15 members with varying coins in guild X
- WHEN the coins leaderboard is queried with limit 10 and offset 0
- THEN the result contains the top 10 members by coins

#### Scenario: Leaderboard pagination

- GIVEN 25 members with XP in guild X
- WHEN the XP leaderboard is queried with limit 10 and offset 10
- THEN the result contains members ranked 11–20 by XP

### Requirement: Dashboard economy config sync via Realtime CDC

Dashboard economy config writes MUST NOT call any inbound bot webhook. Cache invalidation MUST rely on outbound Supabase Realtime CDC (`cache-sync-realtime`).

#### Scenario: Economy config write does not call webhook

- GIVEN the dashboard writes an economy config change to Supabase
- WHEN the Supabase write succeeds
- THEN the Server Action returns success without POSTing to a bot webhook endpoint

#### Scenario: Bot invalidates via Realtime

- GIVEN the bot Realtime subscriber is connected
- WHEN Supabase emits an economy-related config change for guild G
- THEN the bot invalidates the relevant cache for G
