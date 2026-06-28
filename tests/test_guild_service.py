"""Unit tests for bot.services.guild_service.GuildService.

Covers the guild-config spec scenarios:
    - Cache hit → returns cached GuildConfig immediately
    - Cache miss → DB fetch → cache populate → return
    - No DB row → return defaults (nb!, es)
    - save_config → DB upsert + cache invalidation
    - on_guild_join → insert defaults
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.core.cache import TTLCache
from bot.models.guild import GuildConfig
from bot.services.guild_service import GuildService


# ---------------------------------------------------------------------------
# get_config — cache hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_config_cache_hit(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
    sample_config: GuildConfig,
) -> None:
    """When the config is cached, get_config() MUST return it without DB call."""
    guild_id = sample_config.id
    cache_key = f"{guild_id}:config"
    cache.set(cache_key, sample_config, ttl=300)

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    result = await service.get_config(guild_id)

    assert result is sample_config
    mock_db.get_guild.assert_not_called()


# ---------------------------------------------------------------------------
# get_config — cache miss, DB has row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_config_cache_miss_db_hit(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
    sample_config: GuildConfig,
) -> None:
    """Cache miss MUST fall back to DB; a returned row populates the cache."""
    guild_id = sample_config.id
    cache_key = f"{guild_id}:config"

    # Simulate a DB row (camelCase keys per Supabase convention).
    mock_db.get_guild.return_value = {
        "id": sample_config.id,
        "prefix": sample_config.prefix,
        "language": sample_config.language,
        "modRoleId": sample_config.mod_role_id,
        "logChannelId": None,
        "ticketCategoryId": None,
        "logEnabled": False,
        "welcomeEnabled": False,
        "active": True,
    }

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    result = await service.get_config(guild_id)

    # Returned from DB.
    assert result.id == sample_config.id
    assert result.prefix == sample_config.prefix
    assert result.language == sample_config.language
    assert result.mod_role_id == sample_config.mod_role_id

    mock_db.get_guild.assert_awaited_once_with(guild_id)

    # Cache MUST be populated for subsequent reads.
    cached = cache.get(cache_key)
    assert cached is not None
    assert cached.id == sample_config.id


# ---------------------------------------------------------------------------
# get_config — cache miss, no DB row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_config_no_db_row_returns_defaults(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
) -> None:
    """When no DB row exists, get_config() MUST return defaults (nb!, es)."""
    guild_id = "111222333"
    mock_db.get_guild.return_value = None

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    result = await service.get_config(guild_id)

    assert result.id == guild_id
    assert result.prefix == "nb!"
    assert result.language == "es"
    assert result.mod_role_id is None

    mock_db.get_guild.assert_awaited_once_with(guild_id)


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_config_upserts_and_invalidates_cache(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
    sample_config: GuildConfig,
) -> None:
    """save_config() MUST upsert to DB, invalidate the cache entry, and re-read."""
    guild_id = sample_config.id
    cache_key = f"{guild_id}:config"

    # Pre-populate cache with a stale value.
    cache.set(cache_key, "STALE", ttl=300)

    # DB row for the re-read after invalidation.
    mock_db.get_guild.return_value = {
        "id": sample_config.id,
        "prefix": sample_config.prefix,
        "language": sample_config.language,
        "modRoleId": sample_config.mod_role_id,
        "logChannelId": None,
        "ticketCategoryId": None,
        "logEnabled": False,
        "welcomeEnabled": False,
        "active": True,
    }

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    await service.save_config(sample_config)

    # DB upsert was called.
    mock_db.upsert_guild.assert_awaited_once_with(sample_config)

    # Cache was re-populated (via the re-read in save_config).
    cached = cache.get(cache_key)
    assert cached is not None
    assert cached.id == sample_config.id

    # Mod-role cache was synced.
    guild_id_int = int(guild_id)
    assert mod_role_cache.get(guild_id_int) == sample_config.mod_role_id


# ---------------------------------------------------------------------------
# on_guild_join
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_guild_join_inserts_defaults(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
) -> None:
    """on_guild_join() MUST upsert default config (nb!, es) and set cache."""
    guild_id = "999888777"
    cache_key = f"{guild_id}:config"

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    result = await service.on_guild_join(guild_id)

    # Returns a fresh default config.
    assert result.id == guild_id
    assert result.prefix == "nb!"
    assert result.language == "es"

    # DB upsert was called with the default config.
    mock_db.upsert_guild.assert_awaited_once()
    upserted = mock_db.upsert_guild.call_args[0][0]
    assert upserted.id == guild_id
    assert upserted.prefix == "nb!"
    assert upserted.language == "es"

    # Cache was populated.
    cached = cache.get(cache_key)
    assert cached is not None
    assert cached.id == guild_id
    assert cached.prefix == "nb!"


# ---------------------------------------------------------------------------
# mod_role_cache sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mod_role_cache_synced_on_get(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
    sample_config: GuildConfig,
) -> None:
    """When get_config reads a config with mod_role_id, the cache dict MUST be updated."""
    guild_id = sample_config.id
    guild_id_int = int(guild_id)

    mock_db.get_guild.return_value = {
        "id": sample_config.id,
        "prefix": sample_config.prefix,
        "language": sample_config.language,
        "modRoleId": sample_config.mod_role_id,
        "logChannelId": None,
        "ticketCategoryId": None,
        "logEnabled": False,
        "welcomeEnabled": False,
        "active": True,
    }

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    await service.get_config(guild_id)

    assert mod_role_cache.get(guild_id_int) == sample_config.mod_role_id


@pytest.mark.asyncio
async def test_mod_role_cache_cleared_when_none(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
    default_config: GuildConfig,
) -> None:
    """When config has no mod_role_id, the mod-role cache entry MUST be removed."""
    guild_id = default_config.id
    guild_id_int = int(guild_id)

    # Pre-populate with a stale mod role.
    mod_role_cache[guild_id_int] = "old_role"

    mock_db.get_guild.return_value = {
        "id": guild_id,
        "prefix": "nb!",
        "language": "es",
        "modRoleId": None,
        "logChannelId": None,
        "ticketCategoryId": None,
        "logEnabled": False,
        "welcomeEnabled": False,
        "active": True,
    }

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    await service.get_config(guild_id)

    assert guild_id_int not in mod_role_cache


# ---------------------------------------------------------------------------
# deactivate_guild / reactivate_guild
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivate_guild_sets_active_false(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
    sample_config: GuildConfig,
) -> None:
    """deactivate_guild() MUST set active=False, persist, and invalidate cache."""
    guild_id = sample_config.id
    cache_key = f"{guild_id}:config"

    # get_config returns the sample_config.
    mock_db.get_guild.return_value = {
        "id": sample_config.id,
        "prefix": sample_config.prefix,
        "language": sample_config.language,
        "modRoleId": sample_config.mod_role_id,
        "logChannelId": None,
        "ticketCategoryId": None,
        "logEnabled": False,
        "welcomeEnabled": False,
        "active": True,
    }

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    await service.deactivate_guild(guild_id)

    # active flag was toggled.
    assert mock_db.upsert_guild.await_count >= 1
    upserted = mock_db.upsert_guild.call_args[0][0]
    assert upserted.active is False

    # Cache was re-populated (via save_config → get_config re-read).
    cached = cache.get(cache_key)
    assert cached is not None


@pytest.mark.asyncio
async def test_reactivate_guild_sets_active_true(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
    sample_config: GuildConfig,
) -> None:
    """reactivate_guild() MUST set active=True, persist, and invalidate cache."""
    guild_id = sample_config.id
    cache_key = f"{guild_id}:config"

    # get_config returns the sample_config with active=False.
    mock_db.get_guild.return_value = {
        "id": sample_config.id,
        "prefix": sample_config.prefix,
        "language": sample_config.language,
        "modRoleId": sample_config.mod_role_id,
        "logChannelId": None,
        "ticketCategoryId": None,
        "logEnabled": False,
        "welcomeEnabled": False,
        "active": False,
    }

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    await service.reactivate_guild(guild_id)

    # active flag was toggled back.
    assert mock_db.upsert_guild.await_count >= 1
    upserted = mock_db.upsert_guild.call_args[0][0]
    assert upserted.active is True

    # Cache was re-populated.
    cached = cache.get(cache_key)
    assert cached is not None
