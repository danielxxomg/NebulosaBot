-- ============================================================================
-- Migration 003: Economy Config
-- NebulosaBot — Guild Economy System
-- ============================================================================
-- Run this against your Supabase SQL editor or via `supabase db push`.
-- Rollback: DROP TABLE economy_config + ALTER TABLE member DROP dailyStreak, lastDailyReset.
--
-- Dependencies: Migration 001 (guild, member tables must exist)

-- ----------------------------------------------------------------------------
-- Economy Config — per-guild tunable economy parameters
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS economy_config (
    "guildId"           TEXT PRIMARY KEY REFERENCES guild(id) ON DELETE CASCADE,
    "dailyReward"       INTEGER NOT NULL DEFAULT 100,
    "dailyCooldownHours" INTEGER NOT NULL DEFAULT 24,
    "xpPerMessage"      INTEGER NOT NULL DEFAULT 10,
    "xpCooldownSeconds" INTEGER NOT NULL DEFAULT 60,
    "levelBaseXp"       INTEGER NOT NULL DEFAULT 100,
    "levelMultiplier"   REAL NOT NULL DEFAULT 1.5,
    "levelRoles"        JSONB NOT NULL DEFAULT '{}',
    "levelUpChannelId"  TEXT
);

-- ----------------------------------------------------------------------------
-- Member — add daily streak tracking columns
-- ----------------------------------------------------------------------------
ALTER TABLE member ADD COLUMN IF NOT EXISTS "dailyStreak"    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE member ADD COLUMN IF NOT EXISTS "lastDailyReset" TIMESTAMPTZ;

-- ----------------------------------------------------------------------------
-- Index — optimize leaderboard queries (ORDER BY xp DESC, coins DESC)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_member_guild_xp ON member ("guildId", xp DESC);
CREATE INDEX IF NOT EXISTS idx_member_guild_coins ON member ("guildId", coins DESC);
