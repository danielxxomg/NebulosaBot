"""Unit tests for bot.services.guild_service.GuildService.

Covers the guild-config spec scenarios:
    - Cache hit → returns cached GuildConfig immediately
    - Cache miss → DB fetch → cache populate → return
    - No DB row → return defaults (nb!, es)
    - save_config → DB upsert + cache invalidation
    - on_guild_join → insert defaults
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.core.cache import TTLCache
from bot.models.greeting_config import GreetingConfig
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


@pytest.mark.asyncio
async def test_greeting_config_delegates_to_greeting_service(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
) -> None:
    """GuildService MUST delegate greeting ownership instead of duplicating fields."""
    expected = GreetingConfig(guild_id="123456789")
    greeting_service = MagicMock()
    greeting_service.get_config = AsyncMock(return_value=expected)
    greeting_service.save_config = AsyncMock()
    service = GuildService(
        db=mock_db,
        cache=cache,
        mod_role_cache=mod_role_cache,
        greeting_service=greeting_service,
    )

    result = await service.get_greeting_config("123456789")
    await service.save_greeting_config(result)

    assert result == expected
    greeting_service.get_config.assert_awaited_once_with("123456789")
    greeting_service.save_config.assert_awaited_once_with(expected)
    mock_db.get_greeting_config.assert_not_called()
    mock_db.upsert_greeting_config.assert_not_called()


@pytest.mark.asyncio
async def test_greeting_config_requires_delegated_service(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
) -> None:
    """GuildService must not create a second greeting persistence owner."""
    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)

    with pytest.raises(RuntimeError, match="GreetingService must be configured"):
        await service.get_greeting_config("123456789")


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


# ---------------------------------------------------------------------------
# update_guild_panel — cache invalidation after DB write
# (ticket-panel-persistence, Phase 1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_guild_panel_invalidates_cache_after_success(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
    sample_config: GuildConfig,
) -> None:
    """update_guild_panel() MUST invalidate {guild_id}:config cache after DB write succeeds."""
    guild_id = sample_config.id
    cache_key = f"{guild_id}:config"

    # Pre-populate cache with stale config.
    cache.set(cache_key, sample_config, ttl=300)
    assert cache.get(cache_key) is not None

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    await service.update_guild_panel(guild_id, "msg-123", "ch-456")

    # DB method was called with correct args.
    mock_db.update_guild_panel.assert_awaited_once_with(guild_id, "msg-123", "ch-456")

    # Cache entry was invalidated.
    assert cache.get(cache_key) is None


@pytest.mark.asyncio
async def test_update_guild_panel_does_not_invalidate_on_db_failure(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
    sample_config: GuildConfig,
) -> None:
    """update_guild_panel() MUST NOT invalidate cache if DB write fails."""
    guild_id = sample_config.id
    cache_key = f"{guild_id}:config"

    # Pre-populate cache.
    cache.set(cache_key, sample_config, ttl=300)

    # DB write fails.
    mock_db.update_guild_panel.side_effect = Exception("Supabase timeout")

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    with pytest.raises(Exception, match="Supabase timeout"):
        await service.update_guild_panel(guild_id, "msg-123", "ch-456")

    # Cache was NOT invalidated — the failed write should not clear the cache.
    assert cache.get(cache_key) is not None


@pytest.mark.asyncio
async def test_update_guild_panel_supports_nullable_ids(
    cache: TTLCache,
    mock_db: AsyncMock,
    mod_role_cache: dict[int, str],
    sample_config: GuildConfig,
) -> None:
    """update_guild_panel(message_id=None, channel_id=None) MUST clear panel IDs in DB and invalidate cache."""
    guild_id = sample_config.id
    cache_key = f"{guild_id}:config"

    cache.set(cache_key, sample_config, ttl=300)

    service = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
    await service.update_guild_panel(guild_id, None, None)

    mock_db.update_guild_panel.assert_awaited_once_with(guild_id, None, None)
    assert cache.get(cache_key) is None


# ---------------------------------------------------------------------------
# PR1 Phase 2: GuildConfig permission_matrix round-trip (guild-config spec)
# ---------------------------------------------------------------------------


class TestGuildConfigPermissionMatrix:
    """PR1 2.1-2.2 — GuildConfig.from_db_row/to_db_dict round-trips permissionMatrix."""

    def test_round_trip_preserves_matrix_and_other_fields(self) -> None:
        """Round-trip permissionMatrix={"moderation.ban":["roleA"]} preserves prefix/language/matrix."""
        from bot.models.guild import GuildConfig

        row = {
            "id": "guild-xyz",
            "prefix": "nb!",
            "language": "es",
            "modRoleId": "mod-1",
            "permissionMatrix": {"moderation.ban": ["roleA"]},
            "logChannelId": None,
            "logEnabled": False,
            "welcomeEnabled": False,
            "active": True,
        }
        config = GuildConfig.from_db_row(row)
        assert config.permission_matrix == {"moderation.ban": ["roleA"]}
        assert config.prefix == "nb!"
        assert config.language == "es"
        assert config.mod_role_id == "mod-1"

        out = config.to_db_dict()
        assert out["permissionMatrix"] == {"moderation.ban": ["roleA"]}
        assert out["prefix"] == "nb!"
        assert out["language"] == "es"
        assert out["modRoleId"] == "mod-1"

    def test_empty_matrix_round_trips_as_empty_dict(self) -> None:
        """Empty/missing permissionMatrix round-trips as {}."""
        from bot.models.guild import GuildConfig

        row = {"id": "g1", "prefix": "nb!", "language": "es"}
        config = GuildConfig.from_db_row(row)
        assert config.permission_matrix == {}
        out = config.to_db_dict()
        assert out["permissionMatrix"] == {}

    def test_unknown_permission_keys_tolerated(self) -> None:
        """Unknown key {"unknown.perm":["roleX"]} loads without error."""
        from bot.models.guild import GuildConfig

        row = {"id": "g1", "permissionMatrix": {"unknown.perm": ["roleX"]}}
        config = GuildConfig.from_db_row(row)
        assert config.permission_matrix == {"unknown.perm": ["roleX"]}
        # stored but never grants — can() will deny unknown (tested in checks)
        out = config.to_db_dict()
        assert out["permissionMatrix"] == {"unknown.perm": ["roleX"]}

    def test_alias_maps_permission_matrix(self) -> None:
        """GuildConfig._db_aliases maps permissionMatrix ↔ permission_matrix."""
        from bot.models.guild import GuildConfig

        gc = GuildConfig(id="g1")
        assert gc._db_aliases["permissionMatrix"] == "permission_matrix"


# ---------------------------------------------------------------------------
# PR1 Phase 3: GuildService cache ride (guild-config spec)
# ---------------------------------------------------------------------------


class TestGuildServiceMatrixCacheRide:
    """PR1 3.1 — matrix rides {guild_id}:config, no bare perm_matrix key, CDC eviction."""

    @pytest.mark.asyncio
    async def test_matrix_read_from_cache_no_extra_fetch(
        self, cache: TTLCache, mock_db: AsyncMock, mod_role_cache: dict[int, str]
    ) -> None:
        """When config is cached, matrix is available without extra DB fetch."""
        from bot.core.cache import cache_key as ck_fn
        from bot.models.guild import GuildConfig
        from bot.services.guild_service import GuildService

        guild_id = "999000111"
        config = GuildConfig(id=guild_id, prefix="nb!", language="es", permission_matrix={"moderation.ban": ["roleA"]})
        # Pre-populate cache via cache_key(guild_id, "config")
        cache.set(ck_fn(guild_id, "config"), config, ttl=300)
        # Ensure no bare key exists
        assert cache.get("perm_matrix") is None
        assert cache.get(f"{guild_id}:perm_matrix") is None

        svc = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
        loaded = await svc.get_config(guild_id)
        assert loaded.permission_matrix == {"moderation.ban": ["roleA"]}
        mock_db.get_guild.assert_not_called()
        # Second read also from cache
        loaded2 = await svc.get_config(guild_id)
        assert loaded2.permission_matrix == {"moderation.ban": ["roleA"]}
        mock_db.get_guild.assert_not_called()

    @pytest.mark.asyncio
    async def test_cdc_invalidate_guild_evicts_matrix(
        self, cache: TTLCache, mock_db: AsyncMock, mod_role_cache: dict[int, str]
    ) -> None:
        """CDC invalidate_guild evicts the matrix (it lives inside config)."""
        from bot.core.cache import cache_key as ck_fn
        from bot.models.guild import GuildConfig
        from bot.services.guild_service import GuildService

        guild_id = "999000222"
        config = GuildConfig(id=guild_id, permission_matrix={"moderation.ban": ["roleA"]})
        cache.set(ck_fn(guild_id, "config"), config, ttl=300)
        svc = GuildService(db=mock_db, cache=cache, mod_role_cache=mod_role_cache)
        # Confirm cached
        assert (await svc.get_config(guild_id)).permission_matrix == {"moderation.ban": ["roleA"]}
        mock_db.get_guild.assert_not_called()

        # CDC invalidates guild
        cache.invalidate_guild(guild_id)
        assert cache.get(ck_fn(guild_id, "config")) is None

        # Next read re-fetches (DB now returns different matrix)
        mock_db.get_guild.return_value = {
            "id": guild_id,
            "prefix": "nb!",
            "language": "es",
            "permissionMatrix": {"moderation.ban": ["roleB"]},
            "modRoleId": None,
            "logChannelId": None,
            "logEnabled": False,
            "welcomeEnabled": False,
            "active": True,
        }
        reloaded = await svc.get_config(guild_id)
        assert reloaded.permission_matrix == {"moderation.ban": ["roleB"]}
        mock_db.get_guild.assert_awaited_once_with(guild_id)

    def test_no_bare_perm_matrix_cache_key_in_source(self) -> None:
        """Source MUST NOT contain a guild-global bare perm_matrix key (leak guard)."""
        import pathlib
        import re

        src = pathlib.Path("bot/services/guild_service.py").read_text(encoding="utf-8")
        # Forbid cache_key(<literal>, "perm_matrix") or bare "...:perm_matrix" without guild.
        assert not re.search(r'cache_key\s*\(\s*["\']perm_matrix["\']', src), (
            "GuildService MUST NOT use bare perm_matrix as cache_key entity"
        )
        assert '":perm_matrix"' not in src, "GuildService MUST NOT construct bare perm_matrix key"
        # Also check checks.py doesn't construct its own bare key
        src2 = pathlib.Path("bot/utils/checks.py").read_text(encoding="utf-8")
        assert not re.search(r'cache_key\s*\(\s*["\']perm_matrix["\']', src2)
        assert '":perm_matrix"' not in src2
