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
-- LIVE SYNC: This migration is applied to the live Supabase project
-- (ref vozkcckiybebhcclrasa) and `supabase migration list` reports 024/024
-- (schema_migrations recorded). The structural tests in test_migrations.py
-- guard the SQL shape; the live state is confirmed via the linked project's
-- migration list. Re-running is safe due to IF NOT EXISTS on all 3 statements.
-- ----------------------------------------------------------------------------
ALTER TABLE guild ADD COLUMN IF NOT EXISTS "permissionMatrix" JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_infraction_warn_decay ON infraction ("createdAt")
  WHERE type = 'WARN' AND active = true;

CREATE INDEX IF NOT EXISTS idx_infraction_tempban_expiry ON infraction ("expiresAt")
  WHERE type = 'BAN' AND active = true AND "expiresAt" IS NOT NULL;
