-- ============================================================================
-- Migration 024: Permission matrix JSONB + partial indexes (voice-moderation-permissions PR1)
-- NebulosaBot — additive permissionMatrix on guild + 2 partial indexes on infraction
-- ============================================================================
-- Additive & idempotent: existing guild rows get '{}'::jsonb; indexes use IF NOT EXISTS.
-- Validate live schema_migrations before apply (version 024 not already recorded).
-- Rollback: DROP INDEX IF EXISTS idx_infraction_warn_decay;
--          DROP INDEX IF EXISTS idx_infraction_tempban_expiry;
--          ALTER TABLE guild DROP COLUMN IF EXISTS "permissionMatrix";
-- Dependencies: 001 (guild, infraction with expiresAt/createdAt) + 023 (RLS)
-- ----------------------------------------------------------------------------
ALTER TABLE guild ADD COLUMN IF NOT EXISTS "permissionMatrix" JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_infraction_warn_decay ON infraction ("createdAt")
  WHERE type = 'WARN' AND active = true;

CREATE INDEX IF NOT EXISTS idx_infraction_tempban_expiry ON infraction ("expiresAt")
  WHERE type = 'BAN' AND active = true AND "expiresAt" IS NOT NULL;
