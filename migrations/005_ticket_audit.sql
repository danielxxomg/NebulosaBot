-- ============================================================================
-- Migration 005: Ticket Audit Table + Transfer Normalization + Note Dedup Index
-- NebulosaBot — Ticket Invariant Layer (B5)
-- ============================================================================
-- Idempotent & additive: safe to re-run. Adds:
--   1. ticket_audit table (RLS enabled, no anon policies — service-role
--      queries with .eq("guildId"); app-level FK only, no DB FK per project
--      convention).
--   2. Composite note index (ticketId, authorId, createdAt DESC) for the
--      2-second dedup window query.
--   3. Transfer normalization — back up then fix legacy rows where
--      "claimedBy" was set but status stayed 'open' (the pre-invariant
--      transfer bug). Decision #3a.
--   4. Guarded weekly pg_cron retention job (90 days).
--
-- Rollback:
--   DROP TABLE IF EXISTS ticket_audit;
--   DROP INDEX IF EXISTS idx_ticket_note_ticket_author_created;
--   SELECT cron.unschedule('ticket_audit_retention');
-- ============================================================================

-- ----------------------------------------------------------------------------
-- ticket_audit — append-only operation log (app-level FK; no DB FK)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_audit (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "guildId"   TEXT NOT NULL,
    "ticketId"  UUID NOT NULL,
    action      TEXT NOT NULL,
    "actorId"   TEXT,
    outcome     TEXT NOT NULL CHECK (outcome IN ('success', 'denied', 'error')),
    reason      TEXT,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- Indexes — history lookup, guild-scoped timeline, guild+action aggregation
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ticket_audit_ticket_history
    ON ticket_audit ("guildId", "ticketId", "createdAt" DESC);
CREATE INDEX IF NOT EXISTS idx_ticket_audit_guild_created
    ON ticket_audit ("guildId", "createdAt" DESC);
CREATE INDEX IF NOT EXISTS idx_ticket_audit_guild_action
    ON ticket_audit ("guildId", action);

-- ----------------------------------------------------------------------------
-- ticket_note — author+created composite for the 2s dedup window query
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ticket_note_ticket_author_created
    ON ticket_note ("ticketId", "authorId", "createdAt" DESC);

-- ----------------------------------------------------------------------------
-- Row Level Security on ticket_audit (no anon policies; service-role only).
-- The service_role bypasses RLS; anon/authenticated get nothing by default,
-- so dashboard and bot queries MUST use the service role AND filter by
-- "guildId" in application code.
-- ----------------------------------------------------------------------------
ALTER TABLE ticket_audit ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------------------------------------------
-- Transfer normalization — back up legacy rows where "claimedBy" was set but
-- status stayed 'open' (the pre-invariant transfer bug), then fix them.
-- The backup table is idempotent (CREATE TABLE IF NOT EXISTS AS SELECT) so
-- re-running does not clobber the original snapshot.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_backup_claimed_open_20260706 AS
    SELECT * FROM ticket WHERE "claimedBy" IS NOT NULL AND status = 'open';

UPDATE ticket SET status = 'claimed'
    WHERE "claimedBy" IS NOT NULL AND status = 'open';

-- ----------------------------------------------------------------------------
-- pg_cron — weekly retention (90 days). Guarded so re-running does not create
-- a duplicate job: schedule only if no job named 'ticket_audit_retention'
-- exists in cron.job. Requires the pg_cron extension to be enabled on the
-- Supabase project (enable via Dashboard > Database > Extensions if absent).
-- The CREATE EXTENSION below is idempotent and ensures pg_cron is available
-- before the DO block references cron.job / cron.schedule.
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_cron;
DO $guard$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM cron.job WHERE jobname = 'ticket_audit_retention'
    ) THEN
        PERFORM cron.schedule(
            'ticket_audit_retention',
            '0 3 * * 0',
            $$DELETE FROM ticket_audit WHERE "createdAt" < now() - interval '90 days'$$
        );
    END IF;
END $guard$;
