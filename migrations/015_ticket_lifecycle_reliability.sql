-- Migration 015: Ticket lifecycle reliability
-- Idempotent: uses IF NOT EXISTS / IF EXISTS so re-applying is safe.
--
-- 1. Add nullable closeReason column for close-reason tracking
-- 2. Create unique invariant indexes after the live duplicate preflight passes
-- 3. Guard and drop obsolete ticket_backup_claimed_open_20260706 snapshots
--
-- Rollout precondition: the read-only integrity preflight MUST report zero
-- duplicate active slots, active channels, normalized active category names,
-- and guild ticket numbers before this migration is applied.

-- 1. Add closeReason column (nullable — existing rows keep NULL)
ALTER TABLE public.ticket
    ADD COLUMN IF NOT EXISTS "closeReason" TEXT;

-- 2a. One active categorized ticket per guild/user/category.
CREATE UNIQUE INDEX IF NOT EXISTS idx_ticket_active_slot
    ON public.ticket ("guildId", "authorId", "categoryId")
    WHERE status IN ('open', 'claimed')
      AND "categoryId" IS NOT NULL;

-- 2b. One active ticket per Discord channel (zombie detection lookup).
CREATE UNIQUE INDEX IF NOT EXISTS idx_ticket_active_channel
    ON public.ticket ("channelId")
    WHERE status IN ('open', 'claimed');

-- 2c. One normalized active category name per guild.
CREATE UNIQUE INDEX IF NOT EXISTS idx_ticket_category_active_name
    ON public.ticket_category ("guildId", lower(btrim(name)))
    WHERE active = true;

-- 2d. Ticket numbers remain unique within a guild.
CREATE UNIQUE INDEX IF NOT EXISTS idx_ticket_guild_ticket_number
    ON public.ticket ("guildId", "ticketNumber");

DO $$ DECLARE has_rows BOOLEAN; BEGIN
    IF to_regclass('public.ticket_backup_claimed_open_20260706') IS NOT NULL THEN
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM public.ticket_backup_claimed_open_20260706 LIMIT 1)' INTO has_rows;
        IF has_rows THEN RAISE EXCEPTION 'Refusing to drop non-empty legacy recovery snapshot'; END IF;
    END IF; END $$;

DROP TABLE IF EXISTS public.ticket_backup_claimed_open_20260706;
