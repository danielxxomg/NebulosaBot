"""GuildService — cache-first guild configuration management.

Implements the cache-first read pattern from the architecture:
    1. Try RAM cache
    2. Cache miss → fetch from Supabase
    3. Populate cache with TTL
    4. Return GuildConfig

Also updates ``bot._guild_mod_role_cache`` so ``is_mod()`` checks in
``bot/utils/checks.py`` can resolve the moderator role without a DB hit.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.constants import FALLBACK_PREFIX
from bot.core.i18n import set_guild_language
from bot.models.guild import GuildConfig

if TYPE_CHECKING:
    from bot.core.cache import TTLCache
    from bot.core.database import Database

logger = logging.getLogger(__name__)

CACHE_KEY_TEMPLATE = "{guild_id}:config"
CACHE_TTL = 300  # 5 minutes — matches design


class GuildService:
    """Manages per-guild configuration with a cache-first strategy.

    Args:
        db: The bot's :class:`~bot.core.database.Database` instance.
        cache: The bot's :class:`~bot.core.cache.TTLCache` instance.
        mod_role_cache: A ``dict[int, str]`` on the bot instance where
            ``is_mod()`` looks up the moderator role ID.  This service
            keeps it in sync with the database.
    """

    __slots__ = ("_cache", "_db", "_mod_role_cache")

    def __init__(
        self,
        db: Database,
        cache: TTLCache,
        mod_role_cache: dict[int, str],
    ) -> None:
        self._db = db
        self._cache = cache
        self._mod_role_cache = mod_role_cache

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    async def get_config(self, guild_id: str) -> GuildConfig:
        """Return the guild configuration, using cache-first resolution.

        Flow:
            1. Cache hit → return cached ``GuildConfig`` immediately.
            2. Cache miss → fetch from database.
            3. If DB row exists → build config, populate cache, return.
            4. If DB row missing → return defaults (prefix=``nb!``,
               language=``es``) — row will be created lazily on first save.
        """
        cache_key = CACHE_KEY_TEMPLATE.format(guild_id=guild_id)

        # --- cache hit ---
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("GuildService cache HIT for guild %s", guild_id)
            set_guild_language(guild_id, cached.language)
            return cached

        # --- cache miss → DB ---
        logger.debug("GuildService cache MISS for guild %s — fetching from DB", guild_id)
        row = await self._db.get_guild(guild_id)

        config: GuildConfig
        if row is not None:
            config = GuildConfig.from_db_row(row)
        else:
            # No row yet — use defaults. The row will be upserted on first
            # save or on_guild_join.
            config = GuildConfig(id=guild_id, prefix=FALLBACK_PREFIX, language="es")

        # Populate cache and mod-role lookup.
        self._cache.set(cache_key, config, ttl=CACHE_TTL)
        self._sync_mod_role_cache(guild_id, config)
        set_guild_language(guild_id, config.language)

        return config

    async def save_config(self, config: GuildConfig) -> None:
        """Persist a guild configuration to the database and refresh caches.

        Performs a Supabase upsert so it works for both new and existing
        guilds.
        """
        await self._db.upsert_guild(config)

        # Invalidate stale cache entry so the next read picks up the new row.
        cache_key = CACHE_KEY_TEMPLATE.format(guild_id=config.id)
        self._cache.invalidate(cache_key)

        # Re-read through cache-first path to ensure consistency.
        await self.get_config(config.id)

    async def deactivate_guild(self, guild_id: str) -> None:
        """Soft-delete a guild by setting its ``active`` flag to ``False``.

        Invalidates the cache so the next read picks up the updated row.
        """
        config = await self.get_config(guild_id)
        config.active = False
        await self.save_config(config)

    async def reactivate_guild(self, guild_id: str) -> None:
        """Re-activate a previously deactivated guild.

        Sets ``active = True`` and invalidates the cache.
        """
        config = await self.get_config(guild_id)
        config.active = True
        await self.save_config(config)

    async def on_guild_join(self, guild_id: str) -> GuildConfig:
        """Insert default configuration for a freshly joined guild.

        Defaults (from proposal decisions):
            prefix    = ``nb!``
            language  = ``es`` (Spanish)

        Returns the newly created ``GuildConfig``.
        """
        config = GuildConfig(id=guild_id, prefix=FALLBACK_PREFIX, language="es")

        await self._db.upsert_guild(config)

        cache_key = CACHE_KEY_TEMPLATE.format(guild_id=guild_id)
        self._cache.set(cache_key, config, ttl=CACHE_TTL)
        self._sync_mod_role_cache(guild_id, config)
        set_guild_language(guild_id, config.language)

        logger.info(
            "New guild joined: %s — defaults inserted (prefix=%s, lang=%s)",
            guild_id,
            config.prefix,
            config.language,
        )
        return config

    async def ensure_guild_exists(self, guild_id: str) -> None:
        """Ensure a guild config row exists without overwriting custom config.

        Idempotent backfill used at startup (``on_ready``) for guilds the bot
        was already a member of — ``on_guild_join`` only fires for joins that
        happen during the running session. Delegates to
        :meth:`Database.ensure_guild_exists` (INSERT ... ON CONFLICT DO NOTHING).

        After ensuring the row exists, loads the config through the
        cache-first path so the i18n language map is published.
        """
        await self._db.ensure_guild_exists(guild_id)
        # Load through cache-first path to publish guild language to i18n.
        await self.get_config(guild_id)

    # ----------------------------------------------------------------
    # Internal
    # ----------------------------------------------------------------

    def _sync_mod_role_cache(self, guild_id: str, config: GuildConfig) -> None:
        """Keep ``bot._guild_mod_role_cache`` in sync with the config.

        The ``is_mod()`` check in ``bot/utils/checks.py`` reads this
        dict to resolve the moderator role without a DB query.
        """
        try:
            guild_id_int = int(guild_id)
        except (ValueError, TypeError):
            logger.warning("Cannot convert guild_id %r to int for mod-role cache", guild_id)
            return

        if config.mod_role_id is not None:
            self._mod_role_cache[guild_id_int] = config.mod_role_id
        else:
            self._mod_role_cache.pop(guild_id_int, None)
