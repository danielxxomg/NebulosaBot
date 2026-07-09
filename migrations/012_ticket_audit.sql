-- ============================================================================
-- Migration 012: Ticket Audit Table (applied live 2026-07-09)
-- NebulosaBot — Parity with remote apply_migration 012_ticket_audit
-- ============================================================================
-- NOTE: The same SQL lived in migrations/005_ticket_audit.sql but was NEVER
-- applied to production under that name. Remote already had a different
-- 005_rls_secure_default. This file documents the live 012 apply for
-- disaster-recovery / fresh environments. Idempotent.
-- ============================================================================

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

CREATE INDEX IF NOT EXISTS idx_ticket_audit_ticket_history
    ON ticket_audit ("guildId", "ticketId", "createdAt" DESC);
CREATE INDEX IF NOT EXISTS idx_ticket_audit_guild_created
    ON ticket_audit ("guildId", "createdAt" DESC);
CREATE INDEX IF NOT EXISTS idx_ticket_audit_guild_action
    ON ticket_audit ("guildId", action);

CREATE INDEX IF NOT EXISTS idx_ticket_note_ticket_author_created
    ON ticket_note ("ticketId", "authorId", "createdAt" DESC);

ALTER TABLE ticket_audit ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS ticket_backup_claimed_open_20260706 AS
    SELECT * FROM ticket WHERE "claimedBy" IS NOT NULL AND status = 'open';

UPDATE ticket SET status = 'claimed'
    WHERE "claimedBy" IS NOT NULL AND status = 'open';

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
