-- Migration 008: Enable RLS on ticket_note (reproducibility — DB already has RLS enabled)
-- Idempotent: ALTER TABLE ENABLE RLS is safe to re-run
ALTER TABLE ticket_note ENABLE ROW LEVEL SECURITY;
