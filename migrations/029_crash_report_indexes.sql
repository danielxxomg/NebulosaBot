-- ============================================================================
-- Migration 029: crash_report table + crash purge cron + index hygiene
-- NebulosaBot — clean-1.0 S3 (data-retention + index hygiene)
-- ============================================================================
-- Creates crash_report(id, guildId NULLABLE, command, traceback, createdAt)
-- and its 30-day TTL purge (retention_setting key 'crash'). Also handles
-- index hygiene per spec: add member(updatedAt) index, drop duplicate
-- idx_ticket_note_created.
--
-- Idempotent & safe to re-run:
--   - crash_report: CREATE TABLE IF NOT EXISTS
--   - indexes: CREATE INDEX IF NOT EXISTS / DROP INDEX IF EXISTS
--   - cron: DO $guard$ IF NOT EXISTS cron.job → cron.schedule
--   - All DDL uses IF NOT EXISTS / IF EXISTS guards
--
-- Rollback: SELECT cron.unschedule('retention_purge_crash_reports');
--           DROP TABLE IF EXISTS crash_report;
--           DROP INDEX IF EXISTS idx_member_updated_at;
--           CREATE INDEX IF NOT EXISTS idx_ticket_note_created ON ticket_note ("ticketId", "createdAt" DESC);
-- Dependencies: 028 (retention_setting, purge fns), 019 (ticket_note)
-- ============================================================================

CREATE TABLE IF NOT EXISTS crash_report (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "guildId"  TEXT,
    command    TEXT,
    traceback  TEXT NOT NULL,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crash_report_created_at ON crash_report ("createdAt" DESC);
CREATE INDEX IF NOT EXISTS idx_crash_report_guild_created ON crash_report ("guildId", "createdAt" DESC);

-- Index hygiene: add member(updatedAt), drop duplicate idx_ticket_note_created
CREATE INDEX IF NOT EXISTS idx_member_updated_at ON member ("updatedAt");
DROP INDEX IF EXISTS idx_ticket_note_created;

-- Crash purge function is already in 028 (purge_expired_crash_reports); if 029
-- is applied without 028, ensure it exists here as well (idempotent).
CREATE OR REPLACE FUNCTION purge_expired_crash_reports() RETURNS void AS $$
DECLARE
    _ttl INT;
BEGIN
    SELECT days INTO _ttl FROM retention_setting WHERE key = 'crash';
    IF _ttl IS NULL THEN _ttl := 30; END IF;
    DELETE FROM crash_report WHERE "createdAt" < now() - (_ttl || ' days')::interval;
END;
$$ LANGUAGE plpgsql;

-- Idempotent cron schedule for crash purge (guarded; 028 also schedules it)
DO $guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'retention_purge_crash_reports') THEN
        PERFORM cron.schedule('retention_purge_crash_reports', '0 5 * * *', $$SELECT purge_expired_crash_reports()$$);
    END IF;
END $guard$;
