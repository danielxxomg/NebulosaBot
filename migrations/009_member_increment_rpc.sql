-- Migration 009: Member increment RPC functions
-- Replaces N+1 (get_member + update) patterns with atomic SQL functions.
-- Each function uses INSERT ... ON CONFLICT DO UPDATE for upsert safety.
-- SECURITY DEFINER allows the function to bypass RLS.
-- search_path is pinned to 'public' to prevent search_path injection.

-- 1. increment_member_xp — atomic XP increment + lastXpGain timestamp
CREATE OR REPLACE FUNCTION public.increment_member_xp(
    p_guild_id TEXT,
    p_user_id TEXT,
    p_amount INTEGER
)
RETURNS TABLE(xp BIGINT, level INTEGER)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    INSERT INTO public.member ("guildId", "userId", xp, level, coins, warnings, "lastXpGain")
    VALUES (p_guild_id, p_user_id, GREATEST(p_amount, 0), 0, 0, 0, NOW())
    ON CONFLICT ("guildId", "userId") DO UPDATE
        SET xp = GREATEST(public.member.xp + p_amount, 0),
            "lastXpGain" = NOW()
    RETURNING public.member.xp, public.member.level;
END;
$$;

-- 2. increment_member_coins — atomic coin increment
CREATE OR REPLACE FUNCTION public.increment_member_coins(
    p_guild_id TEXT,
    p_user_id TEXT,
    p_amount BIGINT
)
RETURNS TABLE(coins BIGINT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    INSERT INTO public.member ("guildId", "userId", xp, level, coins, warnings)
    VALUES (p_guild_id, p_user_id, 0, 0, GREATEST(p_amount, 0), 0)
    ON CONFLICT ("guildId", "userId") DO UPDATE
        SET coins = GREATEST(public.member.coins + p_amount, 0)
    RETURNING public.member.coins;
END;
$$;

-- 3. increment_member_warnings — atomic warning count increment
CREATE OR REPLACE FUNCTION public.increment_member_warnings(
    p_guild_id TEXT,
    p_user_id TEXT,
    p_amount INTEGER
)
RETURNS TABLE(warnings INTEGER)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    INSERT INTO public.member ("guildId", "userId", xp, level, coins, warnings)
    VALUES (p_guild_id, p_user_id, 0, 0, 0, GREATEST(p_amount, 0))
    ON CONFLICT ("guildId", "userId") DO UPDATE
        SET warnings = GREATEST(public.member.warnings + p_amount, 0)
    RETURNING public.member.warnings;
END;
$$;

-- 4. set_member_daily — atomic daily claim (coins + streak + timestamps)
CREATE OR REPLACE FUNCTION public.set_member_daily(
    p_guild_id TEXT,
    p_user_id TEXT,
    p_coin_amount BIGINT,
    p_streak INTEGER,
    p_last_daily_reset TIMESTAMPTZ,
    p_last_daily TIMESTAMPTZ
)
RETURNS TABLE(coins BIGINT, "dailyStreak" INTEGER, "lastDailyReset" TIMESTAMPTZ, "lastDaily" TIMESTAMPTZ)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    INSERT INTO public.member ("guildId", "userId", xp, level, coins, warnings, "dailyStreak", "lastDailyReset", "lastDaily")
    VALUES (p_guild_id, p_user_id, 0, 0, GREATEST(p_coin_amount, 0), 0, p_streak, p_last_daily_reset, p_last_daily)
    ON CONFLICT ("guildId", "userId") DO UPDATE
        SET coins = GREATEST(public.member.coins + p_coin_amount, 0),
            "dailyStreak" = p_streak,
            "lastDailyReset" = p_last_daily_reset,
            "lastDaily" = p_last_daily
    RETURNING public.member.coins, public.member."dailyStreak", public.member."lastDailyReset", public.member."lastDaily";
END;
$$;

-- Least-privilege: revoke from PUBLIC, grant only to Supabase roles
REVOKE ALL ON FUNCTION
    public.increment_member_xp(TEXT, TEXT, INTEGER),
    public.increment_member_coins(TEXT, TEXT, BIGINT),
    public.increment_member_warnings(TEXT, TEXT, INTEGER),
    public.set_member_daily(TEXT, TEXT, BIGINT, INTEGER, TIMESTAMPTZ, TIMESTAMPTZ)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    public.increment_member_xp(TEXT, TEXT, INTEGER),
    public.increment_member_coins(TEXT, TEXT, BIGINT),
    public.increment_member_warnings(TEXT, TEXT, INTEGER),
    public.set_member_daily(TEXT, TEXT, BIGINT, INTEGER, TIMESTAMPTZ, TIMESTAMPTZ)
TO anon, authenticated, service_role;
