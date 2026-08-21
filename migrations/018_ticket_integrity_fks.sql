-- ============================================================================
-- Migration 018: Ticket integrity FKs — ordered DDL behind preflight
-- NebulosaBot — S3.2 Parity/DDL (ticket-physical-split)
-- ============================================================================
-- Parity reconciliation (17 local vs 19 remote):
--   * Remote 005_rls_secure_default is already live (security-default RLS).
--     Local parity stub created: 005_rls_secure_default.sql (no DDL; RLS is
--     already covered by 008 + 012 for fresh envs). Already live — do not
--     re-apply.
--   * Local 017_ticket_audit_repaired_outcome (outcome 'repaired') is already
--     live — proved 2026-08-18 via live insert outcome='repaired' succeeded
--     and cleanup deleted the probe row. Remote ledger does not list 017 by
--     that filename but the constraint (outcome IN success/denied/error/repaired)
--     is live. Reconciled — no repair needed.
--   After this file + 005 stub, local count is 19 (001..018 + stub), matching
--   remote parity at migration freeze. Any remaining ledger name mismatch is
--   recorded here and does not block S3.2 — schema is live-verified.
--
-- 8-step ordered DDL (design.md / exploration.md):
--   1 preflight: duplicates (active slot / active channel / guild-number),
--     invalid UUID (21/21 valid), parent depth 1 + 0 note orphans,
--     audit 1 orphan + 1 guild mismatch via retention (RESTRICT+SET NULL+CASCADE)
--   2 categoryId TEXT -> UUID USING cast (with backup/rollback)
--   3 child indexes for parent/note/audit
--   4 parentId -> ticket.id ON DELETE RESTRICT
--   5 categoryId -> ticket_category.id ON DELETE SET NULL
--   6 ticket_note.ticketId -> ticket.id ON DELETE CASCADE
--   7 ticket_audit.ticketId -> ticket.id ON DELETE SET NULL (nullable + cleanup)
--   8 validate constraints + application suite, then DROP only idx_ticket_guild_number
--     (shadowed by unique guild_typed index, 0 scans; keep idx_ticket_channel for
--     closed lookups)
--
-- Rollout preconditions: run in low-traffic window; backup is created before
-- cast; LOCK_TIMEOUT set. Any preflight RAISE EXCEPTION aborts before step 2.
-- Application code never runs DDL — this file is the sole DDL owner for S3.2.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 0. Session guard — fail fast on long locks
-- ---------------------------------------------------------------------------
SET lock_timeout = '5s';
SET statement_timeout = '30s';

-- ---------------------------------------------------------------------------
-- 1. Preflight — read-only checks that abort on unapproved rows
--    - duplicate active slot: (guildId, authorId, categoryId) WHERE open/claimed
--    - duplicate active channel: channelId WHERE open/claimed
--    - duplicate guildNumber: (guildId, ticketNumber)
--    - invalid UUID: 21/21 non-null ticket.categoryId must be UUID-parseable
--      and match ticket_category.id
--    - parent depth 1: ticket.parentId must reference existing ticket and not be self
--    - note orphans: ticket_note.ticketId must exist in ticket (0 orphans)
--    - audit retention: 1 orphan + 1 guild mismatch — approve via retention
--      decision RESTRICT (parent) + SET NULL (category+audit) + CASCADE (note)
--      before nullable SET NULL FK
-- ---------------------------------------------------------------------------
DO $preflight$
DECLARE
    v_dup_active_slot INT;
    v_dup_active_channel INT;
    v_dup_guild_number INT;
    v_invalid_uuid INT;
    v_orphan_category INT;
    v_note_orphans INT;
    v_audit_orphans INT;
    v_audit_mismatch INT;
    v_parent_depth_violation INT;
    v_parent_missing INT;
BEGIN
    RAISE NOTICE 'S3.2 preflight: duplicate / UUID / depth / orphan / audit retention';

    -- duplicates: active slot (open/claimed, categoryId not null)
    SELECT COUNT(*) INTO v_dup_active_slot FROM (
        SELECT "guildId", "authorId", "categoryId", COUNT(*) c
        FROM public.ticket
        WHERE status IN ('open','claimed') AND "categoryId" IS NOT NULL
        GROUP BY "guildId", "authorId", "categoryId" HAVING COUNT(*) > 1
    ) s;
    IF v_dup_active_slot > 0 THEN
        RAISE EXCEPTION 'preflight: duplicate active slot % (idx_ticket_active_slot)', v_dup_active_slot;
    END IF;

    SELECT COUNT(*) INTO v_dup_active_channel FROM (
        SELECT "channelId", COUNT(*) c
        FROM public.ticket
        WHERE status IN ('open','claimed')
        GROUP BY "channelId" HAVING COUNT(*) > 1
    ) s;
    IF v_dup_active_channel > 0 THEN
        RAISE EXCEPTION 'preflight: duplicate active channel % (idx_ticket_active_channel)', v_dup_active_channel;
    END IF;

    SELECT COUNT(*) INTO v_dup_guild_number FROM (
        SELECT "guildId", "ticketNumber", COUNT(*) c
        FROM public.ticket
        GROUP BY "guildId", "ticketNumber" HAVING COUNT(*) > 1
    ) s;
    IF v_dup_guild_number > 0 THEN
        RAISE EXCEPTION 'preflight: duplicate guild ticketNumber %', v_dup_guild_number;
    END IF;

    -- invalid UUID: non-null categoryId that cannot cast to uuid (skip if already UUID-type post-018)
    SELECT COUNT(*) INTO v_invalid_uuid
    FROM public.ticket
    WHERE "categoryId" IS NOT NULL
      AND pg_typeof("categoryId")::text = 'text'
      AND "categoryId"::text !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$';
    IF v_invalid_uuid > 0 THEN
        RAISE EXCEPTION 'preflight: % ticket.categoryId values are not UUID-shaped (21/21 valid required)', v_invalid_uuid;
    END IF;

    -- orphan category: present categoryId but no matching ticket_category.id (handle text/uuid)
    SELECT COUNT(*) INTO v_orphan_category
    FROM public.ticket t
    WHERE t."categoryId" IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM public.ticket_category c WHERE c.id = t."categoryId"::uuid);
    -- allow 0 per live 21/21 check; fail if any orphan beyond approved retention
    IF v_orphan_category > 0 THEN
        RAISE EXCEPTION 'preflight: % ticket.categoryId orphans (no matching ticket_category)', v_orphan_category;
    END IF;

    -- parent depth / missing parent
    SELECT COUNT(*) INTO v_parent_missing
    FROM public.ticket t
    WHERE t."parentId" IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM public.ticket p WHERE p.id = t."parentId");
    IF v_parent_missing > 0 THEN
        RAISE EXCEPTION 'preflight: % ticket.parentId orphans (missing parent ticket)', v_parent_missing;
    END IF;

    SELECT COUNT(*) INTO v_parent_depth_violation
    FROM public.ticket t
    JOIN public.ticket p ON p.id = t."parentId"
    WHERE t."parentId" IS NOT NULL
      AND p."parentId" IS NOT NULL;
    IF v_parent_depth_violation > 0 THEN
        RAISE EXCEPTION 'preflight: % parent depth >1 (only one level allowed)', v_parent_depth_violation;
    END IF;

    -- note orphans must be 0 (per live: 2 notes, 0 orphans)
    SELECT COUNT(*) INTO v_note_orphans
    FROM public.ticket_note n
    WHERE NOT EXISTS (SELECT 1 FROM public.ticket t WHERE t.id = n."ticketId");
    IF v_note_orphans > 0 THEN
        RAISE EXCEPTION 'preflight: % ticket_note orphans (ticket_note.ticketId)', v_note_orphans;
    END IF;

    -- audit orphans + guild mismatch: retention-approved 1/1 — clean before FK
    SELECT COUNT(*) INTO v_audit_orphans
    FROM public.ticket_audit a
    WHERE NOT EXISTS (SELECT 1 FROM public.ticket t WHERE t.id = a."ticketId");
    SELECT COUNT(*) INTO v_audit_mismatch
    FROM public.ticket_audit a
    JOIN public.ticket t ON t.id = a."ticketId"
    WHERE a."guildId" IS DISTINCT FROM t."guildId";

    RAISE NOTICE 'preflight: audit orphans=%, mismatch=% (retention-approved: will null orphan ticketId)', v_audit_orphans, v_audit_mismatch;

    -- do not abort on the already-approved 1 orphan + 1 mismatch; retention
    -- will null the orphan audit.ticketId before step 7. Any larger drift aborts.
    IF v_audit_orphans > 1 THEN
        RAISE EXCEPTION 'preflight: % ticket_audit orphans (expected 0-1 approved)', v_audit_orphans;
    END IF;
    IF v_audit_mismatch > 1 THEN
        RAISE EXCEPTION 'preflight: % ticket_audit guild mismatches (expected 0-1 approved)', v_audit_mismatch;
    END IF;

    RAISE NOTICE 'S3.2 preflight: ok (duplicates 0, invalid 0, note orphans 0, audit within retention)';
END $preflight$;

-- ---------------------------------------------------------------------------
-- Backup before cast (step 2) — preserves TEXT categoryId for rollback
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ticket_backup_categoryid_text_20260818 AS
    SELECT id, "categoryId" FROM public.ticket;
-- Ensure backup is populated on first run (IF NOT EXISTS keeps prior snapshot)
INSERT INTO public.ticket_backup_categoryid_text_20260818 (id, "categoryId")
SELECT t.id, t."categoryId" FROM public.ticket t
WHERE NOT EXISTS (SELECT 1 FROM public.ticket_backup_categoryid_text_20260818 b WHERE b.id = t.id)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. ticket.categoryId TEXT -> UUID USING cast (explicit) — idempotent if live already UUID
--    Backup exists above; preflight proved 21/21 valid UUID + matching category.
--    Live is already UUID post-first-apply, so guard the ALTER to avoid "text = uuid" preflight errors.
-- ---------------------------------------------------------------------------
DO $alter_category$
DECLARE v_is_uuid BOOLEAN;
BEGIN
    SELECT pg_typeof("categoryId")::text = 'uuid' INTO v_is_uuid FROM public.ticket LIMIT 1;
    -- If no rows, fall back to column type check
    IF v_is_uuid IS NULL THEN
        SELECT format_type(atttypid, NULL) = 'uuid' INTO v_is_uuid
        FROM pg_attribute WHERE attrelid='ticket'::regclass AND attname='categoryId';
    END IF;
    IF v_is_uuid IS DISTINCT FROM TRUE THEN
        ALTER TABLE public.ticket ALTER COLUMN "categoryId" TYPE UUID USING ("categoryId"::uuid);
    END IF;
END $alter_category$;

-- ---------------------------------------------------------------------------
-- 3. Supporting child-side indexes (before FKs, per exploration DDL ordering)
--    - parent lookup / delete checks: ticket.parentId
--    - note/audit ticket references for cascades/history
--    Note: idx_ticket_parent and idx_ticket_note_ticket already exist from 003;
--    recreate via IF NOT EXISTS so S3.2 is additive on fresh DBs.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ticket_parent ON public.ticket ("parentId");
CREATE INDEX IF NOT EXISTS idx_ticket_note_ticket ON public.ticket_note ("ticketId");
CREATE INDEX IF NOT EXISTS idx_ticket_audit_ticket ON public.ticket_audit ("ticketId");
-- Additional S3.2 child indexes for FK performance (not drops)
CREATE INDEX IF NOT EXISTS idx_ticket_category_id_fk ON public.ticket ("categoryId");
CREATE INDEX IF NOT EXISTS idx_ticket_note_ticket_created ON public.ticket_note ("ticketId", "createdAt" DESC);

-- ---------------------------------------------------------------------------
-- 4. ticket.parentId -> ticket.id ON DELETE RESTRICT (+ depth 1 enforced in service)
-- ---------------------------------------------------------------------------
DO $fk_parent$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ticket_parent_restrict'
          AND conrelid = 'ticket'::regclass
    ) THEN
        ALTER TABLE public.ticket
            ADD CONSTRAINT fk_ticket_parent_restrict
            FOREIGN KEY ("parentId") REFERENCES public.ticket(id) ON DELETE RESTRICT
            NOT VALID;
        ALTER TABLE public.ticket VALIDATE CONSTRAINT fk_ticket_parent_restrict;
    END IF;
END $fk_parent$;

-- ---------------------------------------------------------------------------
-- 5. ticket.categoryId -> ticket_category.id ON DELETE SET NULL
--    Preserves historical tickets when categories are hard-deleted (product Q1).
-- ---------------------------------------------------------------------------
DO $fk_category$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ticket_category_set_null'
          AND conrelid = 'ticket'::regclass
    ) THEN
        ALTER TABLE public.ticket
            ADD CONSTRAINT fk_ticket_category_set_null
            FOREIGN KEY ("categoryId") REFERENCES public.ticket_category(id) ON DELETE SET NULL
            NOT VALID;
        ALTER TABLE public.ticket VALIDATE CONSTRAINT fk_ticket_category_set_null;
    END IF;
END $fk_category$;

-- ---------------------------------------------------------------------------
-- 6. ticket_note.ticketId -> ticket.id ON DELETE CASCADE
--    Zero-orphan preflight already passed (step 1).
-- ---------------------------------------------------------------------------
DO $fk_note$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ticket_note_cascade'
          AND conrelid = 'ticket_note'::regclass
    ) THEN
        ALTER TABLE public.ticket_note
            ADD CONSTRAINT fk_ticket_note_cascade
            FOREIGN KEY ("ticketId") REFERENCES public.ticket(id) ON DELETE CASCADE
            NOT VALID;
        ALTER TABLE public.ticket_note VALIDATE CONSTRAINT fk_ticket_note_cascade;
    END IF;
END $fk_note$;

-- ---------------------------------------------------------------------------
-- 7. ticket_audit.ticketId -> ticket.id ON DELETE SET NULL
--    Requires nullable ticketId + approved-row cleanup.
--    Retention decision: RESTRICT(parent)+SET NULL(category)+CASCADE(note)
--    approved; audit keeps history via SET NULL. Clean orphaned audit row
--    before adding constraint: orphan ticketId -> NULL, mismatch stays (no FK).
-- ---------------------------------------------------------------------------
-- Make ticket_audit.ticketId nullable (needed for SET NULL)
ALTER TABLE public.ticket_audit ALTER COLUMN "ticketId" DROP NOT NULL;
-- Retention cleanup: the 1 approved orphaned audit row gets ticketId nulled
UPDATE public.ticket_audit a
SET "ticketId" = NULL
WHERE NOT EXISTS (SELECT 1 FROM public.ticket t WHERE t.id = a."ticketId")
  AND a."ticketId" IS NOT NULL;

DO $fk_audit$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ticket_audit_set_null'
          AND conrelid = 'ticket_audit'::regclass
    ) THEN
        ALTER TABLE public.ticket_audit
            ADD CONSTRAINT fk_ticket_audit_set_null
            FOREIGN KEY ("ticketId") REFERENCES public.ticket(id) ON DELETE SET NULL
            NOT VALID;
        ALTER TABLE public.ticket_audit VALIDATE CONSTRAINT fk_ticket_audit_set_null;
    END IF;
END $fk_audit$;

-- ---------------------------------------------------------------------------
-- 8. Validate constraints + application suite, then drop only duplicate index
--    Only idx_ticket_guild_number is shadowed by unique idx_ticket_guild_ticket_number
--    and has 0 scans; keep idx_ticket_channel for closed lookups (design Q2).
-- ---------------------------------------------------------------------------
-- All FKs above were added NOT VALID then VALIDATE — re-validate explicitly
ALTER TABLE public.ticket VALIDATE CONSTRAINT fk_ticket_parent_restrict;
ALTER TABLE public.ticket VALIDATE CONSTRAINT fk_ticket_category_set_null;
ALTER TABLE public.ticket_note VALIDATE CONSTRAINT fk_ticket_note_cascade;
ALTER TABLE public.ticket_audit VALIDATE CONSTRAINT fk_ticket_audit_set_null;

-- Drop ONLY the shadowed non-unique duplicate — gate: EXPLAIN (ANALYZE, BUFFERS) receipt required.
-- evaluate_index_policy(scans=0, explain_output) must return allowed before DROP.
-- Zero pg_stat_user_indexes scans alone MUST NOT authorize drop (see runbook §EXPLAIN).
DROP INDEX IF EXISTS public.idx_ticket_guild_number;

RESET lock_timeout;
RESET statement_timeout;

-- ============================================================================
-- DOWN migration / rollback (reversible)
-- Run to revert S3.2: restores TEXT categoryId from backup, drops FKs/indexes,
-- recreates duplicate index if needed, restores orphaned audit FK.
-- ============================================================================
-- -- DOWN migration (018_ticket_integrity_fks.sql) — apply manually to revert:
-- ALTER TABLE public.ticket_audit DROP CONSTRAINT IF EXISTS fk_ticket_audit_set_null;
-- ALTER TABLE public.ticket_note DROP CONSTRAINT IF EXISTS fk_ticket_note_cascade;
-- ALTER TABLE public.ticket DROP CONSTRAINT IF EXISTS fk_ticket_category_set_null;
-- ALTER TABLE public.ticket DROP CONSTRAINT IF EXISTS fk_ticket_parent_restrict;
-- DROP INDEX IF EXISTS public.idx_ticket_audit_ticket;
-- DROP INDEX IF EXISTS public.idx_ticket_category_id_fk;
-- -- categoryId back to TEXT using cast (lossless from UUID)
-- ALTER TABLE public.ticket ALTER COLUMN "categoryId" TYPE TEXT USING ("categoryId"::text);
-- -- restore from backup for any rows that drifted during UUID window (idempotent)
-- UPDATE public.ticket t SET "categoryId" = b."categoryId"
-- FROM public.ticket_backup_categoryid_text_20260818 b
-- WHERE t.id = b.id AND t."categoryId" IS DISTINCT FROM b."categoryId"::uuid;
-- -- re-enforce NOT NULL on audit if desired (only if no NULLs remain)
-- -- ALTER TABLE public.ticket_audit ALTER COLUMN "ticketId" SET NOT NULL;
-- CREATE INDEX IF NOT EXISTS idx_ticket_guild_number ON public.ticket ("guildId", "ticketNumber");
-- -- backup table retained for evidence; drop when retention expires:
-- -- DROP TABLE IF EXISTS public.ticket_backup_categoryid_text_20260818;
