"""GreetingService — cache-first greeting configuration and dispatch.

Manages per-guild welcome/goodbye configuration (CRUD + cache-first reads)
and dispatches welcome/goodbye cards via ImageService.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.models.greeting_config import GreetingConfig

if TYPE_CHECKING:
    import discord
    from bot.core.cache import TTLCache
    from bot.core.database import Database

logger = logging.getLogger(__name__)

CACHE_KEY_TEMPLATE = "{guild_id}:greeting_config"
CACHE_TTL = 300  # 5 minutes


class GreetingService:
    """Manages per-guild greeting configuration with a cache-first strategy.

    Args:
        db: The bot's :class:`~bot.core.database.Database` instance.
        cache: The bot's :class:`~bot.core.cache.TTLCache` instance.
        image_service: The bot's :class:`~bot.services.image_service.ImageService`
            instance for generating welcome/goodbye cards.
    """

    __slots__ = ("_db", "_cache", "_image_service")

    def __init__(
        self,
        db: Database,
        cache: TTLCache,
        image_service: object,
    ) -> None:
        self._db = db
        self._cache = cache
        self._image_service = image_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_config(self, guild_id: str) -> GreetingConfig:
        """Return the greeting configuration, using cache-first resolution.

        Flow:
            1. Cache hit → return cached ``GreetingConfig`` immediately.
            2. Cache miss → fetch from database.
            3. If DB row exists → build config, populate cache, return.
            4. If DB row missing → return defaults.
        """
        cache_key = CACHE_KEY_TEMPLATE.format(guild_id=guild_id)

        # Cache hit.
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("GreetingService cache HIT for guild %s", guild_id)
            return cached

        # Cache miss → DB.
        logger.debug("GreetingService cache MISS for guild %s — fetching from DB", guild_id)
        row = await self._db.get_greeting_config(guild_id)

        config: GreetingConfig
        if row is not None:
            config = GreetingConfig.from_db_row(row)
        else:
            config = GreetingConfig(guild_id=guild_id)

        # Populate cache.
        self._cache.set(cache_key, config, ttl=CACHE_TTL)
        return config

    async def save_config(self, config: GreetingConfig) -> None:
        """Persist a greeting configuration to the database and invalidate cache.

        Performs a Supabase upsert so it works for both new and existing guilds.
        """
        await self._db.upsert_greeting_config(config)

        cache_key = CACHE_KEY_TEMPLATE.format(guild_id=config.guild_id)
        self._cache.invalidate(cache_key)

    async def dispatch_welcome(self, member: discord.Member) -> None:
        """Send a welcome card/message for *member*, if configured.

        Resolves the greeting config.  If welcome is enabled and a channel
        is set, delegates to ``ImageService.generate_greeting_card()``
        (wired in Phase 2).
        """
        guild_id = str(member.guild.id)
        config = await self.get_config(guild_id)

        if not config.welcome_enabled:
            return
        if not config.welcome_channel_id:
            return

        # Phase 2: generate and send the card via ImageService.
        # card = await asyncio.to_thread(
        #     self._image_service.generate_greeting_card, ...)
        # await channel.send(file=discord.File(card))

        logger.info(
            "dispatch_welcome: enabled for guild %s, channel %s, member %s",
            guild_id, config.welcome_channel_id, member.name,
        )

    async def dispatch_goodbye(self, member: discord.Member) -> None:
        """Send a goodbye card/message for *member*, if configured.

        Resolves the greeting config.  If goodbye is enabled and a channel
        is set, delegates to ``ImageService.generate_greeting_card()``
        (wired in Phase 2).
        """
        guild_id = str(member.guild.id)
        config = await self.get_config(guild_id)

        if not config.goodbye_enabled:
            return
        if not config.goodbye_channel_id:
            return

        # Phase 2: generate and send the card via ImageService.
        # card = await asyncio.to_thread(
        #     self._image_service.generate_greeting_card, ...)
        # await channel.send(file=discord.File(card))

        logger.info(
            "dispatch_goodbye: enabled for guild %s, channel %s, member %s",
            guild_id, config.goodbye_channel_id, member.name,
        )
