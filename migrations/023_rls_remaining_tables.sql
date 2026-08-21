-- ============================================================================
-- Migration 023: RLS on remaining tables (welcome-neon-timer-banana PR3)
-- NebulosaBot — additive ENABLE ROW LEVEL SECURITY (no policies)
-- ============================================================================
-- Additive: enabling RLS with no policies denies anon/publishable/authenticated;
-- service_role bypasses RLS (bot unaffected). Health probe still passes.
-- Validate live schema_migrations before apply (version 023 not already recorded).
-- Rollback: ALTER TABLE <t> DISABLE ROW LEVEL SECURITY; for each of the 7 tables.
-- Dependencies: 008/012 already have RLS on ticket_note/ticket_audit.
-- Tables: guild, member, infraction, ticket, ticket_category, economy_config, greeting_config
-- ----------------------------------------------------------------------------
ALTER TABLE guild ENABLE ROW LEVEL SECURITY;
ALTER TABLE member ENABLE ROW LEVEL SECURITY;
ALTER TABLE infraction ENABLE ROW LEVEL SECURITY;
ALTER TABLE ticket ENABLE ROW LEVEL SECURITY;
ALTER TABLE ticket_category ENABLE ROW LEVEL SECURITY;
ALTER TABLE economy_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE greeting_config ENABLE ROW LEVEL SECURITY;
-- Rollback: DISABLE ROW LEVEL SECURITY (see header)
