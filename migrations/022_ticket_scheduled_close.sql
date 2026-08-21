-- ============================================================================
-- Migration 022: Ticket scheduled-close timer (welcome-neon-timer-banana PR2)
-- NebulosaBot — additive nullable scheduledCloseAt/By + partial index
-- ============================================================================
-- Additive & idempotent: existing rows get NULL scheduledCloseAt/By.
-- Validate live schema_migrations before apply (version 022 not already recorded).
-- Rollback: DROP INDEX IF EXISTS idx_ticket_scheduled_close;
--          ALTER TABLE ticket DROP COLUMN IF EXISTS "scheduledCloseAt";
--          ALTER TABLE ticket DROP COLUMN IF EXISTS "scheduledCloseBy";
-- Dependencies: 015 (lifecycle) — coexists with idx_ticket_active_channel.
-- ----------------------------------------------------------------------------
ALTER TABLE ticket ADD COLUMN IF NOT EXISTS "scheduledCloseAt" TIMESTAMPTZ;
ALTER TABLE ticket ADD COLUMN IF NOT EXISTS "scheduledCloseBy" TEXT;
CREATE INDEX IF NOT EXISTS idx_ticket_scheduled_close ON ticket ("scheduledCloseAt")
  WHERE status IN ('open', 'claimed') AND "scheduledCloseAt" IS NOT NULL;
