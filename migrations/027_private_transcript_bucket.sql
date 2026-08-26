-- ============================================================================
-- Migration 027: Private transcript bucket (S1 transcript triple-path)
-- NebulosaBot — clean-1.0 S1 storage prerequisite
-- ============================================================================
-- Creates the PRIVATE Storage bucket ``transcripts`` used by
-- TranscriptService.deliver() for the durable transcript copy. The object
-- path is ``transcripts/{guildId}/{ticketId}/{filename}`` and carries a
-- 30-day TTL aligned with the retention purge (S3).
--
-- Idempotent & safe to re-run:
--   - INSERT ... ON CONFLICT (id) DO UPDATE ensures re-runs are a no-op
--     when the bucket already exists, and corrects public=true to private
--     when the bucket was created manually with the wrong visibility.
--   - No DDL beyond the single row insert; no extension or function
--     dependency.
--
-- Rollback: DELETE FROM storage.buckets WHERE id = 'transcripts';
--           (fails if objects remain — empty the bucket first)
-- Dependencies: storage schema (Supabase Storage extension)
-- ============================================================================

INSERT INTO storage.buckets (id, name, public)
VALUES ('transcripts', 'transcripts', false)
ON CONFLICT (id) DO UPDATE SET public = false;
