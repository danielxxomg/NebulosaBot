-- ============================================================================
-- Migration 016: Optional Greeting Onboarding Channel
-- NebulosaBot — Welcome/Goodbye System
-- ============================================================================
-- Additive and backwards-compatible: existing greeting_config rows receive NULL.
-- Rollback: ALTER TABLE greeting_config DROP COLUMN IF EXISTS "onboardingChannelId";

ALTER TABLE greeting_config
    ADD COLUMN IF NOT EXISTS "onboardingChannelId" TEXT;
