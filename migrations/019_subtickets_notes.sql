-- ============================================================================
-- Migration 019: Sub-Tickets & Staff Notes (was 003_subtickets_notes.sql)
-- NebulosaBot — Tickets Subsidiados (parent/child derivation + notes)
-- ============================================================================
-- Run this against your Supabase SQL editor or via `supabase db push`.
-- Additive & idempotent: existing tickets are untouched (parentId defaults to
-- NULL). No DB-level FK on ticket.parentId — validation is app-level only,
-- per Supabase Transaction Mode (no FK enforcement). See design.md.
-- Rollback: DROP TABLE IF EXISTS ticket_note;
--           ALTER TABLE ticket DROP COLUMN IF EXISTS "parentId";
-- ============================================================================
-- Identity reconciliation (welcome-svg-foundation hygiene H-7 / GC-1):
-- This file was renamed from 003_subtickets_notes.sql to 019_ to resolve the
-- duplicate 003 prefix (003_economy_config.sql vs 003_subtickets_notes.sql).
-- A raw rename of a *deployed* migration desyncs the live `schema_migrations`
-- table, so the rename was validated/reconciled before it shipped:
--   1. SELECT version, name FROM supabase_migrations.schema_migrations
--      confirmed no row referenced the old 003_subtickets_notes identity in a
--      way that a rename would orphan (the on-disk prefix is cosmetic for
--      already-applied additive DDL — the statements are idempotent).
--   2. The migration body is additive & idempotent (CREATE TABLE IF NOT
--      EXISTS, ADD COLUMN IF NOT EXISTS), so re-applying under the new 019
--      prefix is a no-op against a database that already ran it as 003.
--   3. If a live project had recorded the old prefix, a no-op reconciliation
--      migration recording the identity change would ship instead; the
--      idempotent body above makes the raw rename safe for this project.
-- Re-running this file never changes an already-provisioned database.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Ticket — self-referential parent column (nullable UUID, one level deep)
-- ----------------------------------------------------------------------------
ALTER TABLE ticket
    ADD COLUMN IF NOT EXISTS "parentId" UUID;

-- ----------------------------------------------------------------------------
-- Ticket Note — staff-only annotation (NOT visible to the ticket opener)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_note (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "ticketId" UUID NOT NULL,
    "authorId" TEXT NOT NULL,
    content     TEXT NOT NULL,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- Indexes — parent lookup + note lookups (by ticket, newest-first composite)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ticket_parent ON ticket ("parentId");
CREATE INDEX IF NOT EXISTS idx_ticket_note_ticket ON ticket_note ("ticketId");
CREATE INDEX IF NOT EXISTS idx_ticket_note_created ON ticket_note ("ticketId", "createdAt" DESC);
