"""GreetingService — cache-first greeting configuration and dispatch.

Manages per-guild welcome/goodbye configuration (CRUD + cache-first reads)
and dispatches welcome/goodbye cards via ImageService.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING, Any, Literal, cast

import discord

from bot.core.cache import CACHE_TTL as CORE_GREETING_TTL
from bot.core.cache import cache_key
from bot.core.i18n import t
from bot.models.greeting_config import GreetingConfig

if TYPE_CHECKING:
    from bot.core.cache import TTLCache
    from bot.core.database import Database
    from bot.services.image_service import ImageService

logger = logging.getLogger(__name__)

CACHE_KEY_TEMPLATE = "{guild_id}:greeting_config"
CACHE_TTL = CORE_GREETING_TTL  # re-export from bot.core.cache (DRY; canonical TTL=300)


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
        ck = cache_key(guild_id, "greeting_config")

        # Cache hit.
        cached = self._cache.get(ck)
        if cached is not None:
            logger.debug("GreetingService cache HIT for guild %s", guild_id)
            return cast(GreetingConfig, cached)

        # Cache miss → DB.
        logger.debug("GreetingService cache MISS for guild %s — fetching from DB", guild_id)
        row = await self._db.get_greeting_config(guild_id)

        config = GreetingConfig.from_db_row(row) if row is not None else GreetingConfig(guild_id=guild_id)

        # Populate cache.
        self._cache.set(ck, config, ttl=CACHE_TTL)
        return config

    async def save_config(self, config: GreetingConfig) -> None:
        """Persist a greeting configuration to the database and invalidate cache.

        Performs a Supabase upsert so it works for both new and existing guilds.
        """
        await self._db.upsert_greeting_config(config.guild_id, config)

        ck = cache_key(config.guild_id, "greeting_config")
        self._cache.invalidate(ck)

    async def dispatch_greeting(self, member: discord.Member, kind: Literal["welcome", "goodbye"]) -> None:
        """Unified dispatch for welcome/goodbye — DRY for cache key + card flow.

        Args:
            member: The target member.
            kind: ``"welcome"`` or ``"goodbye"``.
        """
        guild_id = str(member.guild.id)
        config = await self.get_config(guild_id)

        if kind == "welcome":
            enabled = config.welcome_enabled
            channel_id = config.welcome_channel_id
            card_enabled = config.welcome_card_enabled
            message: str | None = config.welcome_message
            card_type: Literal["welcome", "goodbye"] = "welcome"
            filename = "welcome.png"
            title_key = "greetings.card.welcome_title"
            log_prefix = "dispatch_welcome"
        else:
            enabled = config.goodbye_enabled
            channel_id = config.goodbye_channel_id
            card_enabled = config.goodbye_card_enabled
            message = config.goodbye_message
            card_type = "goodbye"
            filename = "goodbye.png"
            title_key = "greetings.card.goodbye_title"
            log_prefix = "dispatch_goodbye"

        if not enabled or not channel_id:
            return

        channel = _resolve_guild_channel(member.guild, channel_id)
        if channel is None:
            logger.warning(
                "%s: channel %s not found for guild %s",
                log_prefix,
                channel_id,
                guild_id,
            )
            return

        if not card_enabled:
            if kind == "welcome":
                await _send_text_only_if_message(
                    cast(discord.abc.Messageable, channel),
                    message or "",
                    member,
                    onboarding_channel_id=config.onboarding_channel_id,
                    normalize_whitespace=True,
                )
            else:
                await _send_text_only_if_message(
                    cast(discord.abc.Messageable, channel),
                    message or "",
                    member,
                )
            return

        avatar_url = _resolve_avatar_url(member)
        buffer: io.BytesIO = await asyncio.to_thread(
            _generate_greeting_card_compatibly,
            self._image_service,
            username=member.display_name,
            avatar_url=avatar_url,
            guild_name=member.guild.name,
            member_count=member.guild.member_count or 0,
            guild_icon_url=_resolve_guild_icon_url(member.guild),
            greeting_title=t(guild_id, title_key),
            member_count_text=t(
                guild_id,
                "greetings.card.member_count",
                count=member.guild.member_count or 0,
            ),
            card_type=card_type,
        )

        file = discord.File(buffer, filename=filename)
        if kind == "welcome":
            content = _compose_welcome_content(member, message, config.onboarding_channel_id)
        else:
            content = _format_template(message or "", member) if message else ""

        await cast(discord.abc.Messageable, channel).send(content=content if content else None, file=file)

        logger.info(
            "%s: sent for guild %s, channel %s, member %s",
            log_prefix,
            guild_id,
            channel_id,
            member.name,
        )

    async def dispatch_welcome(self, member: discord.Member) -> None:
        """Send a welcome card/message for *member*, if configured."""
        await self.dispatch_greeting(member, "welcome")

    async def dispatch_goodbye(self, member: discord.Member) -> None:
        """Send a goodbye card/message for *member*, if configured."""
        await self.dispatch_greeting(member, "goodbye")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _generate_greeting_card_compatibly(image_service: ImageService, **renderer_kwargs: Any) -> io.BytesIO:
    """Use localized renderer inputs while tolerating the frozen old signature."""
    try:
        return image_service.generate_greeting_card(**renderer_kwargs)
    except TypeError as exc:
        message = str(exc)
        if "unexpected keyword argument" not in message or not any(
            keyword in message for keyword in ("greeting_title", "member_count_text", "guild_icon_url")
        ):
            raise
        renderer_kwargs.pop("greeting_title", None)
        renderer_kwargs.pop("member_count_text", None)
        renderer_kwargs.pop("guild_icon_url", None)
        return image_service.generate_greeting_card(**renderer_kwargs)


def _format_template(template: str, member: discord.Member) -> str:
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
    channel: discord.abc.Messageable,
    message_template: str,
    member: discord.Member,
    *,
    onboarding_channel_id: str | None = None,
    normalize_whitespace: bool = False,
) -> None:
    """Send a formatted text-only message to *channel* when the template is set.

    Used by card-disabled dispatch: no file is attached. Welcome messages use
    formatted whitespace as their emptiness gate, while goodbye messages keep
    the historical CTA-free text behavior.
    """
    if normalize_whitespace:
        content = _format_template(message_template, member)
        if content.strip():
            await channel.send(content=content)
        return

    content = _compose_welcome_content(member, message_template, onboarding_channel_id)
    if content:
        await channel.send(content=content)


def _compose_welcome_content(
    member: discord.Member,
    message_template: str | None,
    onboarding_channel_id: str | None,
) -> str:
    """Format welcome text and append a CTA only for an accessible channel."""
    content = _format_template(message_template, member) if message_template else ""
    cta = _resolve_welcome_cta(member, onboarding_channel_id)
    if cta:
        return f"{content}\n{cta}" if content else cta
    return content


def _resolve_welcome_cta(member: discord.Member, channel_id: str | None) -> str | None:
    """Return the localized onboarding CTA when the configured channel is cached."""
    if _resolve_guild_channel(member.guild, channel_id) is None:
        return None
    return t(
        str(member.guild.id),
        "greetings.cta.welcome_onboarding",
        channel=f"<#{channel_id}>",
    )


def _resolve_guild_channel(
    guild: discord.Guild,
    channel_id: str | None,
) -> discord.abc.GuildChannel | None:
    """Resolve a configured channel from the guild cache without API calls."""
    if not channel_id:
        return None
    try:
        return guild.get_channel(int(channel_id))
    except (TypeError, ValueError):
        logger.warning("Invalid greeting channel ID %r for guild %s", channel_id, guild.id)
        return None


def _resolve_avatar_url(member: discord.Member) -> str | None:
    """Return the display avatar URL for *member*, or ``None`` on failure."""
    try:
        return str(member.display_avatar.url)
    except Exception:
        logger.debug("Could not resolve avatar URL for user %s", member.id, exc_info=True)
        return None


def _resolve_guild_icon_url(guild: discord.Guild) -> str | None:
    """Return a cached guild icon URL, or ``None`` when the guild has no icon."""
    try:
        icon = guild.icon
        return str(icon.url) if icon is not None else None
    except Exception:
        logger.debug("Could not resolve guild icon URL for guild %s", guild.id, exc_info=True)
        return None
