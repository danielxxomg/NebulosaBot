-- ============================================================================
-- Migration 007: Realtime Publication
-- NebulosaBot — Add CDC tables to supabase_realtime publication
-- ============================================================================
-- The supabase_realtime publication is already configured in the live
-- Supabase DB (verified via MCP during the cache-sync-realtime audit).
-- This migration exists purely for reproducibility so that fresh
-- environments or disaster-recovery scenarios get the same publication
-- configuration.
--
-- Idempotent: ALTER PUBLICATION ADD TABLE does not support IF NOT EXISTS
-- natively, so we use a DO block that catches the duplicate-object error
-- (SQLSTATE 42710 — duplicate_object) and silently skips it.
-- ============================================================================

DO $$
BEGIN
    ALTER PUBLICATION supabase_realtime ADD TABLE guild, greeting_config, ticket, ticket_note;
EXCEPTION
    WHEN duplicate_object THEN
        -- Publication already contains these tables — safe to ignore.
        NULL;
END;
$$;
