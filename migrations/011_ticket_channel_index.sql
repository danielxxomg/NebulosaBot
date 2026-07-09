-- Migration 011: Add index on ticket ("channelId") for fast lookups.
-- Supports get_ticket_by_channel and update_ticket_last_activity queries.
-- Idempotent: CREATE INDEX IF NOT EXISTS is a no-op if the index already exists.

CREATE INDEX IF NOT EXISTS idx_ticket_channel ON public.ticket ("channelId");
