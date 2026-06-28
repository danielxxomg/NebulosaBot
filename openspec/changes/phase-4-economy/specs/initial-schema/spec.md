# Delta for Initial Schema

## ADDED Requirements

### Requirement: Migration 003

The system MUST provide a Migration 003 that adds the `economy_config` table and `daily_streak`/`last_daily_reset` columns to the `Member` table.

#### Scenario: Run migration 003

- GIVEN Migrations 001 and 002 have been applied
- WHEN Migration 003 runs
- THEN the `economy_config` table exists and the `Member` table has the new columns

### Requirement: economy_config table

The system MUST create an `economy_config` table with columns: `guildId` (PK string), `dailyReward` (int default 100), `dailyCooldownHours` (int default 24), `xpPerMessage` (int default 10), `xpCooldownSeconds` (int default 60), `levelBaseXp` (float default 100.0), `levelMultiplier` (float default 1.5), `levelUpChannelId` (nullable string), `levelRoles` (nullable JSONB).

#### Scenario: economy_config insert

- GIVEN a Guild exists
- WHEN a default economy_config row is inserted
- THEN all defaults are applied and `guildId` is unique

### Requirement: Member economy columns

The system MUST add `daily_streak` (int default 0) and `last_daily_reset` (nullable timestamptz) columns to the `Member` table.

#### Scenario: Member daily fields

- GIVEN a Member row exists
- WHEN the row is queried after Migration 003
- THEN `daily_streak` defaults to 0 and `last_daily_reset` is nullable

### Requirement: Leaderboard indexes

The system SHOULD create indexes on `Member` (`guildId`, `xp` desc) and (`guildId`, `coins` desc).

#### Scenario: Query leaderboard

- GIVEN many members across guilds
- WHEN querying the XP or coins leaderboard for one guild
- THEN the query uses the corresponding index efficiently

## MODIFIED Requirements

### Requirement: Member table

The system MUST create a Member table with columns: `guildId` (FK string), `userId` (FK string), `xp` (bigint default 0), `level` (int default 0), `warnings` (int default 0), `coins` (bigint default 0), `lastDaily` (nullable datetime), `lastXpGain` (nullable datetime), `daily_streak` (int default 0), `last_daily_reset` (nullable timestamptz), composite PK (`guildId`, `userId`).
(Previously: Member table columns were `guildId`, `userId`, `xp`, `level`, `warnings`, `coins`, `lastDaily`, `lastXpGain` with composite PK.)

#### Scenario: Member insert

- GIVEN a Guild and User exist
- WHEN a Member row is inserted
- THEN the composite key is unique and new columns default to 0/null
