-- ============================================================================
-- Migration 004: Greeting Config
-- NebulosaBot — Welcome/Goodbye System
-- ============================================================================
-- Run this against your Supabase SQL editor or via `supabase db push`.
-- Rollback: DROP TABLE greeting_config.
--
-- Dependencies: Migration 001 (guild table must exist)

-- ----------------------------------------------------------------------------
-- Greeting Config — per-guild welcome/goodbye settings
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS greeting_config (
    "guildId"             TEXT PRIMARY KEY REFERENCES guild(id) ON DELETE CASCADE,
    "welcomeEnabled"      BOOLEAN NOT NULL DEFAULT FALSE,
    "goodbyeEnabled"      BOOLEAN NOT NULL DEFAULT FALSE,
    "welcomeChannelId"    TEXT,
    "goodbyeChannelId"    TEXT,
    "welcomeMessage"      TEXT,
    "goodbyeMessage"      TEXT,
    "welcomeCardEnabled"  BOOLEAN NOT NULL DEFAULT TRUE,
    "goodbyeCardEnabled"  BOOLEAN NOT NULL DEFAULT TRUE
);
