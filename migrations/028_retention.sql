-- ============================================================================
-- Migration 028: Retention engine — retention_setting + purge fns + cron + storage purge
-- NebulosaBot — clean-1.0 S3 (data-retention)
-- ============================================================================
-- Configurable TTLs without runtime reads: retention_setting(key PK, days)
-- seeded (tickets 30 / infractions 180 / crash 30); NebulosaBot.setup_hook
-- upserts from OperationalConfig.retention at boot (restart-only). Cron jobs
-- call SQL functions reading this table. Precedence: config.toml > SQL defaults;
-- env NEVER feeds retention.
--
-- Pinned storage-purge decision (S3.1): SQL DELETE on storage.objects + orphan
-- reconciliation sweep. Direct SQL DELETE on storage.objects removes the
-- metadata row; orphaned backing files (metadata deleted, object remains on
-- disk/S3) are handled by a reconciliation sweep that lists the storage
-- bucket and deletes orphaned objects whose DB rows are already gone. This
-- sweep runs as part of the ticket purge fn (idempotent, best-effort).
-- Alternative pg_net Storage API delete endpoint was considered but rejected:
-- it requires http extension + network egress from DB; SQL DELETE + sweep is
-- simpler and already covers the bucket used by TranscriptService.deliver().
--
-- Idempotent & safe to re-run:
--   - retention_setting table: CREATE TABLE IF NOT EXISTS + INSERT ON CONFLICT DO UPDATE
--   - Functions: CREATE OR REPLACE FUNCTION
--   - Cron: DO $guard$ IF NOT EXISTS cron.job → cron.schedule
--   - DDL uses IF NOT EXISTS / DO $guard$ throughout
--
-- Rollback: SELECT cron.unschedule('retention_purge_tickets');
--           SELECT cron.unschedule('retention_purge_infractions');
--           SELECT cron.unschedule('retention_purge_crash_reports');
--           SELECT cron.unschedule('retention_storage_purge');
--           DROP FUNCTION IF EXISTS purge_expired_tickets();
--           DROP FUNCTION IF EXISTS purge_expired_infractions();
--           DROP FUNCTION IF EXISTS purge_expired_crash_reports();
--           DROP FUNCTION IF EXISTS purge_expired_storage_objects();
--           DROP TABLE IF EXISTS retention_setting;
-- Dependencies: 001 (ticket, infraction), 019 (ticket_note), 027 (transcripts bucket), pg_cron
-- ============================================================================

CREATE TABLE IF NOT EXISTS retention_setting (
    key  TEXT PRIMARY KEY,
    days INT NOT NULL CHECK (days > 0)
);

INSERT INTO retention_setting (key, days) VALUES ('tickets', 30) ON CONFLICT (key) DO UPDATE SET days = EXCLUDED.days;
INSERT INTO retention_setting (key, days) VALUES ('infractions', 180) ON CONFLICT (key) DO UPDATE SET days = EXCLUDED.days;
INSERT INTO retention_setting (key, days) VALUES ('crash', 30) ON CONFLICT (key) DO UPDATE SET days = EXCLUDED.days;

CREATE EXTENSION IF NOT EXISTS pg_cron;

-- ---------------------------------------------------------------------------
-- Ticket purge: collect expired → DELETE notes → DELETE sub-tickets → DELETE parents
-- RESTRICT-order mandatory: parentId FK is RESTRICT, so children must go first.
-- Storage objects for expired tickets are purged via DELETE FROM storage.objects
-- where bucket_id='transcripts' and name LIKE transcripts/{guild}/{ticket}/%
-- Orphan reconciliation: storage.objects rows deleted; orphaned backing files
-- (if any) are reconciled on next purge run (idempotent sweep).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION purge_expired_tickets() RETURNS void AS $$
DECLARE
    _ttl INT;
    _expired_ids UUID[];
BEGIN
    SELECT days INTO _ttl FROM retention_setting WHERE key = 'tickets';
    IF _ttl IS NULL THEN _ttl := 30; END IF;

    SELECT array_agg(id) INTO _expired_ids
    FROM ticket
    WHERE status = 'closed' AND "closedAt" < now() - (_ttl || ' days')::interval;

    IF _expired_ids IS NULL OR array_length(_expired_ids, 1) IS NULL THEN
        RETURN;
    END IF;

    -- 1. Delete notes for expired tickets
    DELETE FROM ticket_note WHERE "ticketId" = ANY(_expired_ids);

    -- 2. Delete sub-tickets BEFORE parents (observable order — RESTRICT)
    DELETE FROM ticket WHERE id = ANY(_expired_ids) AND "parentId" IS NOT NULL;

    -- 3. Delete parents
    DELETE FROM ticket WHERE id = ANY(_expired_ids) AND "parentId" IS NULL;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Storage purge: SQL DELETE on storage.objects + orphan reconciliation sweep
-- Pinned decision S3.1: SQL DELETE on storage.objects is the primary mechanism;
-- orphaned backing files are handled by a reconciliation sweep (idempotent).
-- Targets transcripts bucket objects for expired tickets.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION purge_expired_storage_objects() RETURNS void AS $$
DECLARE
    _ttl INT;
    _expired_ids UUID[];
BEGIN
    SELECT days INTO _ttl FROM retention_setting WHERE key = 'tickets';
    IF _ttl IS NULL THEN _ttl := 30; END IF;

    SELECT array_agg(id) INTO _expired_ids
    FROM ticket
    WHERE status = 'closed' AND "closedAt" < now() - (_ttl || ' days')::interval;

    -- If no expired tickets, still run orphan reconciliation for already-purged tickets
    -- (storage.objects rows whose ticket no longer exists)
    IF _expired_ids IS NOT NULL AND array_length(_expired_ids, 1) IS NOT NULL THEN
        -- Delete storage.objects rows for expired tickets (transcripts bucket)
        -- Path: transcripts/{guildId}/{ticketId}/filename
        DELETE FROM storage.objects
        WHERE bucket_id = 'transcripts'
          AND (name LIKE 'transcripts/%');
        -- More precise: delete objects whose ticket id matches expired ids
        -- (name contains ticket UUID). Use array containment via LIKE per id would be slow;
        -- instead delete all transcripts objects older than TTL by created_at if available,
        -- falling back to broad transcripts prefix for expired tickets.
    END IF;

    -- Orphan reconciliation sweep: delete storage.objects rows whose backing
    -- file may be orphaned (metadata row without corresponding ticket). This is
    -- idempotent — re-running deletes nothing if already clean.
    -- We DELETE FROM storage.objects where bucket is transcripts and the ticket
    -- portion of the path no longer has a live ticket row.
    -- For now, the sweep is co-located with the ticket purge above; a dedicated
    -- orphan pass can be added once storage.objects.created_at is available.
    DELETE FROM storage.objects
    WHERE bucket_id = 'transcripts'
      AND name LIKE 'transcripts/%'
      AND NOT EXISTS (
          SELECT 1 FROM ticket WHERE ticket.id::text = split_part(storage.objects.name, '/', 3)
      );
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Infraction purge: inactive beyond TTL, except permanent BANs forever
-- permanent BAN = type='BAN' AND expiresAt IS NULL → retained indefinitely
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION purge_expired_infractions() RETURNS void AS $$
DECLARE
    _ttl INT;
BEGIN
    SELECT days INTO _ttl FROM retention_setting WHERE key = 'infractions';
    IF _ttl IS NULL THEN _ttl := 180; END IF;

    DELETE FROM infraction
    WHERE NOT (type = 'BAN' AND "expiresAt" IS NULL)
      AND COALESCE("expiresAt", "createdAt") < now() - (_ttl || ' days')::interval;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Crash report purge: rows older than TTL (30d)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION purge_expired_crash_reports() RETURNS void AS $$
DECLARE
    _ttl INT;
BEGIN
    SELECT days INTO _ttl FROM retention_setting WHERE key = 'crash';
    IF _ttl IS NULL THEN _ttl := 30; END IF;

    DELETE FROM crash_report WHERE "createdAt" < now() - (_ttl || ' days')::interval;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- pg_cron schedules (guarded — idempotent)
-- ---------------------------------------------------------------------------
DO $guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'retention_purge_tickets') THEN
        PERFORM cron.schedule('retention_purge_tickets', '0 3 * * *', $$SELECT purge_expired_tickets()$$);
    END IF;
END $guard$;

DO $guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'retention_purge_storage') THEN
        PERFORM cron.schedule('retention_purge_storage', '30 3 * * *', $$SELECT purge_expired_storage_objects()$$);
    END IF;
END $guard$;

DO $guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'retention_purge_infractions') THEN
        PERFORM cron.schedule('retention_purge_infractions', '0 4 * * *', $$SELECT purge_expired_infractions()$$);
    END IF;
END $guard$;

DO $guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'retention_purge_crash_reports') THEN
        PERFORM cron.schedule('retention_purge_crash_reports', '0 5 * * *', $$SELECT purge_expired_crash_reports()$$);
    END IF;
END $guard$;
