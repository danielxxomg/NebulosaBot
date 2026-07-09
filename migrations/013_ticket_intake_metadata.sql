-- Migration 013: Add nullable subject and description columns to ticket table.
-- Idempotent: uses IF NOT EXISTS so re-applying is safe.
-- These columns support the ticket intake modal flow (ticket-intake-ux change).

ALTER TABLE ticket
    ADD COLUMN IF NOT EXISTS subject text,
    ADD COLUMN IF NOT EXISTS description text;
