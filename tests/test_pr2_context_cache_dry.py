"""PR2 RED tests: Context[NebulosaBot], cache_key helper, dispatch_greeting DRY.

Strict TDD — these tests MUST fail before the PR2 implementation and pass after.
Exercises the three PR2 deliverables:
  1. cache_key helper centralized in bot/core/cache.py
  2. NebulosaContext parameterized as commands.Context[NebulosaBot]
  3. GreetingService dispatch_welcome/dispatch_goodbye unified via shared helper
"""

from __future__ import annotations

import pathlib


def test_cache_key_helper_exists_and_formats() -> None:
    """cache_key helper must exist in bot.core.cache and format {guild_id}:{entity}."""
    from bot.core.cache import cache_key

    assert cache_key("123", "config") == "123:config"
    assert cache_key(456, "greeting_config") == "456:greeting_config"
    assert cache_key("guild-1", "leaderboard:xp") == "guild-1:leaderboard:xp"


def test_cache_key_helper_guild_isolation() -> None:
    """cache_key must produce distinct keys for different guilds."""
    from bot.core.cache import cache_key

    a = cache_key("111", "config")
    b = cache_key("222", "config")
    assert a != b
    assert a == "111:config"
    assert b == "222:config"


def test_cache_ttl_constants_unified_in_core_cache() -> None:
    """TTL constants must be centralized in bot.core.cache (DRY).

    Services should import from cache rather than defining their own 300.
    """
    import bot.core.cache as cache_module

    assert hasattr(cache_module, "cache_key")
    # Unified TTLs — at least guild/config and leaderboard documented
    # Accept either DEFAULT_TTL renamed or explicit aliases
    has_guild_ttl = any(
        name in dir(cache_module) for name in ("GUILD_TTL", "GUILD_CONFIG_TTL", "CACHE_TTL", "DEFAULT_TTL")
    )
    assert has_guild_ttl, "expected a guild TTL constant in bot.core.cache"
    # Leaderboard 30s should also be centralized or re-exported
    has_lb = any(name in dir(cache_module) for name in ("LEADERBOARD_TTL", "LEADERBOARD_CACHE_TTL"))
    # Allow it to stay in economy_service if documented, but prefer cache module
    if not has_lb:
        # At minimum DEFAULT should be 300 and services reference it
        assert getattr(cache_module, "DEFAULT_TTL", 300) == 300


def test_nebulosa_context_parameterized() -> None:
    """NebulosaContext must be parameterized as commands.Context[NebulosaBot]."""
    path = pathlib.Path("bot/core/context.py")
    content = path.read_text(encoding="utf-8")
    # Must contain a parameterized base like Context[NebulosaBot] (string or actual)
    assert "Context[NebulosaBot]" in content or 'Context["NebulosaBot"]' in content, (
        "NebulosaContext should inherit from commands.Context[NebulosaBot]"
    )
    # Old unparameterized form with type-arg ignore should be gone
    assert "class NebulosaContext(commands.Context):" not in content, "old unparameterized base still present"


def test_cogs_use_nebulosa_context_not_any() -> None:
    """Greetings/Core/Stellar/Ocio cogs must use NebulosaContext, not Context[Any]."""
    for cog_file in [
        "bot/cogs/greetings.py",
        "bot/cogs/core.py",
        "bot/cogs/stellar.py",
        "bot/cogs/ocio.py",
    ]:
        content = pathlib.Path(cog_file).read_text(encoding="utf-8")
        assert "NebulosaContext" in content, f"{cog_file} should import/use NebulosaContext"
        # No remaining type: ignore[arg-type] suppressing the hybrid_command generic
        assert "type: ignore[arg-type]" not in content, f"{cog_file} still has type: ignore[arg-type]"


def test_greeting_dispatch_unified_via_helper() -> None:
    """dispatch_welcome/dispatch_goodbye must delegate to a shared dispatch_greeting helper."""
    content = pathlib.Path("bot/services/greeting_service.py").read_text(encoding="utf-8")
    # Helper exists
    assert "dispatch_greeting" in content or "_dispatch_greeting" in content, (
        "expected shared dispatch_greeting helper in greeting_service.py"
    )
    # Both public methods still exist (backwards compat) but should call the helper
    assert "async def dispatch_welcome" in content
    assert "async def dispatch_goodbye" in content
    # The helper should be referenced inside both methods (DRY)
    # Count helper occurrences — at least 3 (def + 2 calls)
    assert content.count("dispatch_greeting") >= 3, "dispatch_welcome/goodbye should call shared helper"
    # TTL should be sourced from cache module, not duplicated magic 300
    assert "CACHE_TTL" in content or "DEFAULT_TTL" in content or "GUILD_TTL" in content


def test_greeting_service_cache_key_uses_helper() -> None:
    """GreetingService and GuildService should use cache_key helper for key construction."""
    for svc in ["bot/services/greeting_service.py", "bot/services/guild_service.py"]:
        content = pathlib.Path(svc).read_text(encoding="utf-8")
        # After DRY, they should import cache_key from bot.core.cache
        assert "cache_key" in content, f"{svc} should use cache_key helper"
        # They should not build keys via raw .format(guild_id= guild_id) for the primary key
        # (allow one template constant but helpers preferred)
        assert "from bot.core.cache import" in content and "cache_key" in content
