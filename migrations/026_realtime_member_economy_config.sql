-- ============================================================================
-- Migration 026: Realtime member + economy_config publication + updatedAt
-- NebulosaBot — cycle-5-quality-zero S6 (cache-sync-realtime)
-- ============================================================================
-- Extends the supabase_realtime publication with the ``member`` and
-- ``economy_config`` tables so RealtimeCacheSubscriber receives CDC events
-- for them, and adds trigger-maintained ``updatedAt`` columns so the poll
-- fallback can query incrementally instead of full-scanning.
--
-- Idempotent & safe to re-run:
--   - Publication ALTER runs in a DO block catching duplicate_object
--     (SQLSTATE 42710) — verbatim 007_realtime_publication pattern; adding
--     an already-published table is a no-op.
--   - ADD COLUMN IF NOT EXISTS guards both column adds.
--   - Trigger function is CREATE OR REPLACE; triggers use DROP IF EXISTS
--     followed by CREATE TRIGGER.
--
-- Hard ordering: the bot-side _on_write echo-suppression hooks landed in
-- commit 027b636 BEFORE this publication change (spec scenario "Hard
-- ordering is verifiable in history") — inverting the order would let every
-- own RPC write bounce back as an unfiltered echo event.
--
-- updatedAt semantics: INSERT rows take DEFAULT now(); UPDATEs (including
-- RPC increments and upsert ON CONFLICT DO UPDATE paths) fire BEFORE UPDATE
-- triggers. Existing rows are backfilled with now() by the column default,
-- so the incremental poll has no NULL special-casing to do.
--
-- Rollback: ALTER PUBLICATION supabase_realtime DROP TABLE member, economy_config;
--           ALTER TABLE member DROP COLUMN IF EXISTS "updatedAt";
--           ALTER TABLE economy_config DROP COLUMN IF EXISTS "updatedAt";
--           DROP TRIGGER IF EXISTS trg_member_updated_at ON member;
--           DROP TRIGGER IF EXISTS trg_economy_config_updated_at ON economy_config;
--           DROP FUNCTION IF EXISTS set_row_updated_at();
-- Dependencies: 001 (member), 003 (economy_config), 007 (publication)
-- ============================================================================

DO $$
BEGIN
    ALTER PUBLICATION supabase_realtime ADD TABLE member, economy_config;
EXCEPTION
    WHEN duplicate_object THEN
        -- Publication already contains these tables — safe to ignore.
        NULL;
END;
$$;

ALTER TABLE member ADD COLUMN IF NOT EXISTS "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE economy_config ADD COLUMN IF NOT EXISTS "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE OR REPLACE FUNCTION set_row_updated_at() RETURNS trigger AS $$
BEGIN
    NEW."updatedAt" = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_member_updated_at ON member;
CREATE TRIGGER trg_member_updated_at BEFORE UPDATE ON member
FOR EACH ROW EXECUTE FUNCTION set_row_updated_at();

DROP TRIGGER IF EXISTS trg_economy_config_updated_at ON economy_config;
CREATE TRIGGER trg_economy_config_updated_at BEFORE UPDATE ON economy_config
FOR EACH ROW EXECUTE FUNCTION set_row_updated_at();
