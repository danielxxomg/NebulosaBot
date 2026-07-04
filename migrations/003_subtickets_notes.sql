-- ============================================================================
-- Migration 003: Sub-Tickets & Staff Notes
-- NebulosaBot — Tickets Subsidiados (parent/child derivation + notes)
-- ============================================================================
-- Run this against your Supabase SQL editor or via `supabase db push`.
-- Additive & idempotent: existing tickets are untouched (parentId defaults to
-- NULL). No DB-level FK on ticket.parentId — validation is app-level only,
-- per Supabase Transaction Mode (no FK enforcement). See design.md.
-- Rollback: DROP TABLE IF EXISTS ticket_note;
--           ALTER TABLE ticket DROP COLUMN IF EXISTS "parentId";
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
