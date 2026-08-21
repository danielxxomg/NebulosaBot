-- ============================================================================
-- Migration 021: Greeting theme_id (welcome-neon-timer-banana Cycle 2 PR1)
-- NebulosaBot — additive nullable themeId for gaming_neon theme
-- ============================================================================
-- Additive & idempotent: existing rows get NULL themeId → default theme.
-- Validate live schema_migrations before apply (version 021 not already recorded).
-- Rollback: ALTER TABLE greeting_config DROP COLUMN IF EXISTS "themeId";
-- Dependencies: Migration 004 (greeting_config) and 020 (updatedAt)
-- ----------------------------------------------------------------------------
ALTER TABLE greeting_config ADD COLUMN IF NOT EXISTS "themeId" TEXT;
