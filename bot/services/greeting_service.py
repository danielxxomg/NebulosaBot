"""GreetingService — cache-first greeting configuration and dispatch.

Manages per-guild welcome/goodbye configuration (CRUD + cache-first reads)
and dispatches welcome/goodbye cards via ImageService.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING

import discord

from bot.models.greeting_config import GreetingConfig

if TYPE_CHECKING:
    from bot.core.cache import TTLCache
    from bot.core.database import Database
    from bot.services.image_service import ImageService

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

    __slots__ = ("_cache", "_db", "_image_service")

    def __init__(
        self,
        db: Database,
        cache: TTLCache,
    image_service: ImageService,
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
        is set, generates a greeting card via ``ImageService`` and sends it.
        """
        guild_id = str(member.guild.id)
        config = await self.get_config(guild_id)

        if not config.welcome_enabled:
            return
        if not config.welcome_channel_id:
            return

        channel = member.guild.get_channel(int(config.welcome_channel_id))
        if channel is None:
            logger.warning(
                "dispatch_welcome: channel %s not found for guild %s",
                config.welcome_channel_id, guild_id,
            )
            return

        if not config.welcome_card_enabled:
            await _send_text_only_if_message(
                channel, config.welcome_message or "", member
            )
            return

        avatar_url = _resolve_avatar_url(member)
        buffer: io.BytesIO = await asyncio.to_thread(
            self._image_service.generate_greeting_card,
            username=member.display_name,
            avatar_url=avatar_url,
            guild_name=member.guild.name,
            member_count=member.guild.member_count,
            card_type="welcome",
        )

        file = discord.File(buffer, filename="welcome.png")
        message_template = config.welcome_message or ""
        content = _format_template(message_template, member) if message_template else ""

        await channel.send(content=content if content else None, file=file)

        logger.info(
            "dispatch_welcome: sent for guild %s, channel %s, member %s",
            guild_id, config.welcome_channel_id, member.name,
        )

    async def dispatch_goodbye(self, member: discord.Member) -> None:
        """Send a goodbye card/message for *member*, if configured.

        Resolves the greeting config.  If goodbye is enabled and a channel
        is set, generates a goodbye card via ``ImageService`` and sends it.
        """
        guild_id = str(member.guild.id)
        config = await self.get_config(guild_id)

        if not config.goodbye_enabled:
            return
        if not config.goodbye_channel_id:
            return

        channel = member.guild.get_channel(int(config.goodbye_channel_id))
        if channel is None:
            logger.warning(
                "dispatch_goodbye: channel %s not found for guild %s",
                config.goodbye_channel_id, guild_id,
            )
            return

        if not config.goodbye_card_enabled:
            await _send_text_only_if_message(
                channel, config.goodbye_message or "", member
            )
            return

        avatar_url = _resolve_avatar_url(member)
        buffer: io.BytesIO = await asyncio.to_thread(
            self._image_service.generate_greeting_card,
            username=member.display_name,
            avatar_url=avatar_url,
            guild_name=member.guild.name,
            member_count=member.guild.member_count,
            card_type="goodbye",
        )

        file = discord.File(buffer, filename="goodbye.png")
        message_template = config.goodbye_message or ""
        content = _format_template(message_template, member) if message_template else ""

        await channel.send(content=content if content else None, file=file)

        logger.info(
            "dispatch_goodbye: sent for guild %s, channel %s, member %s",
            guild_id, config.goodbye_channel_id, member.name,
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _format_template(template: str, member) -> str:
    """Format a message template string with member placeholders.

    Supported placeholders: ``{mention}``, ``{user}``, ``{server}``.
    Unknown placeholders are left as-is.
    """
    try:
        return template.format(
            mention=member.mention,
            user=member.mention,
            server=member.guild.name,
        )
    except (KeyError, ValueError):
        return template


async def _send_text_only_if_message(
    channel, message_template: str, member
) -> None:
    """Send a formatted text-only message to *channel* when the template is set.

    Used by the card-disabled path: no file is attached, and nothing is sent
    when the template is empty or formats to an empty string.
    """
    content = _format_template(message_template, member) if message_template else ""
    if content:
        await channel.send(content=content)


def _resolve_avatar_url(member) -> str | None:
    """Return the display avatar URL for *member*, or ``None`` on failure."""
    try:
        return str(member.display_avatar.url)
    except Exception:
        logger.debug("Could not resolve avatar URL for user %s", member.id, exc_info=True)
        return None
