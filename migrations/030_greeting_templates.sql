-- ============================================================================
-- Migration 030: Greeting per-kind template columns (greeting-templates S2)
-- NebulosaBot — additive nullable welcomeTemplateId/goodbyeTemplateId
-- ============================================================================
-- Additive & idempotent: existing rows keep NULL per-kind ids → default theme.
-- Backfill: null per-kind columns inherit legacy themeId (COALESCE + IS NULL);
-- rows with NULL themeId stay NULL → default render.
-- Validate live schema_migrations before apply (version 030 not already recorded).
-- Rollback: ALTER TABLE greeting_config DROP COLUMN IF EXISTS "welcomeTemplateId", "goodbyeTemplateId";
-- Dependencies: Migration 004 (greeting_config) and 021 (themeId)
-- ----------------------------------------------------------------------------
ALTER TABLE greeting_config ADD COLUMN IF NOT EXISTS "welcomeTemplateId" TEXT;
ALTER TABLE greeting_config ADD COLUMN IF NOT EXISTS "goodbyeTemplateId" TEXT;
UPDATE greeting_config SET "welcomeTemplateId"=COALESCE("welcomeTemplateId","themeId") WHERE "welcomeTemplateId" IS NULL;
UPDATE greeting_config SET "goodbyeTemplateId"=COALESCE("goodbyeTemplateId","themeId") WHERE "goodbyeTemplateId" IS NULL;
