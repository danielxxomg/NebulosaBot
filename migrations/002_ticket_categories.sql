-- ============================================================================
-- Migration 002: Ticket Categories & Panel Persistence
-- NebulosaBot — Phase 3 Tickets Foundation
-- ============================================================================
-- Run this against your Supabase SQL editor or via `supabase db push`.
-- Rollback: DROP TABLE ticket_category; ALTER TABLE guild DROP COLUMN
-- "ticketPanelMessageId", DROP COLUMN "ticketPanelChannelId";

-- ----------------------------------------------------------------------------
-- Ticket Category
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_category (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "guildId"       TEXT NOT NULL REFERENCES guild(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    emoji           TEXT,
    description     TEXT,
    "position"      INTEGER NOT NULL DEFAULT 0,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- Guild — Panel Persistence Columns
-- ----------------------------------------------------------------------------
ALTER TABLE guild
    ADD COLUMN IF NOT EXISTS "ticketPanelMessageId" TEXT,
    ADD COLUMN IF NOT EXISTS "ticketPanelChannelId" TEXT;

-- ----------------------------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ticket_category_guild ON ticket_category ("guildId");
