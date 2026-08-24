-- 025_drop_ticket_backup_categoryid_text_20260818.sql
-- Cycle 5 — quality zero (S3): drop the ticket backup table created during
-- the categoryid TEXT remediation window (20260818). Destructive but approved:
-- recovery is only via a pre-existing DB dump. Idempotent re-runs are safe.
DROP TABLE IF EXISTS public.ticket_backup_categoryid_text_20260818;
