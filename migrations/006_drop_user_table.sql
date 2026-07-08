-- ============================================================================
-- Migration 006: Drop User Table
-- NebulosaBot — Remove vestigial user table + FK constraints
-- ============================================================================
-- The user table was never populated by the bot and is not referenced by
-- dashboard specs.  All four FK constraints referencing user(id) must be
-- dropped so that member/infraction/ticket inserts succeed without a
-- matching user row.
--
-- Idempotent: every statement uses IF EXISTS.
-- Rollback: re-create the user table and re-add the 4 FK constraints
--           (requires data backfill if any user rows existed, but none did).

-- ----------------------------------------------------------------------------
-- Drop FK constraints referencing user(id)
-- ----------------------------------------------------------------------------
ALTER TABLE member       DROP CONSTRAINT IF EXISTS "member_userId_fkey";
ALTER TABLE infraction   DROP CONSTRAINT IF EXISTS "infraction_targetId_fkey";
ALTER TABLE infraction   DROP CONSTRAINT IF EXISTS "infraction_moderatorId_fkey";
ALTER TABLE ticket       DROP CONSTRAINT IF EXISTS "ticket_authorId_fkey";

-- ----------------------------------------------------------------------------
-- Drop the vestigial user table
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS "user";
