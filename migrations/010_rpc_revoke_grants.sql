-- Migration 010: Revoke EXECUTE on member mutation RPCs from anon and authenticated.
-- Only service_role retains access. Bot uses service_role key, so no code changes needed.
-- Idempotent: REVOKE on a non-existent grant is a no-op in PostgreSQL.

REVOKE EXECUTE ON FUNCTION
    public.increment_member_xp(TEXT, TEXT, INTEGER),
    public.increment_member_coins(TEXT, TEXT, BIGINT),
    public.increment_member_warnings(TEXT, TEXT, INTEGER),
    public.set_member_daily(TEXT, TEXT, BIGINT, INTEGER, TIMESTAMPTZ, TIMESTAMPTZ)
FROM anon, authenticated;
