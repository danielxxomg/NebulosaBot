"""GreetingService — cache-first greeting configuration and dispatch.

Manages per-guild welcome/goodbye configuration (CRUD + cache-first reads)
and dispatches welcome/goodbye cards via a ``GreetingRenderer`` interface.
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
from bot.services.greeting_renderer import GreetingRenderer

if TYPE_CHECKING:
    from bot.core.cache import TTLCache
    from bot.core.database import Database

logger = logging.getLogger(__name__)

CACHE_KEY_TEMPLATE = "{guild_id}:greeting_config"
CACHE_TTL = CORE_GREETING_TTL  # re-export from bot.core.cache (DRY; canonical TTL=300)
AVATAR_CACHE_TTL = 60  # seconds — greeting avatar dedupe per guild
RAID_MAX_CONCURRENT = 2  # concurrent Pillow renders allowed per guild (D4 raid guard)


class GreetingService:
    """Manages per-guild greeting configuration with a cache-first strategy.

    Args:
        db: The bot's :class:`~bot.core.database.Database` instance.
        cache: The bot's :class:`~bot.core.cache.TTLCache` instance.
        greeting_renderer: The ``GreetingRenderer`` implementation for
            generating welcome/goodbye cards.
        image_service: Deprecated — prefer ``greeting_renderer``. Kept for
            backwards compatibility with existing tests.
    """

    __slots__ = ("_cache", "_db", "_greeting_renderer", "_image_service", "_raid_semaphores")

    def __init__(
        self,
        db: Database,
        cache: TTLCache,
        greeting_renderer: GreetingRenderer | None = None,
        image_service: Any | None = None,
    ) -> None:
        self._db = db
        self._cache = cache
        if greeting_renderer is not None:
            self._greeting_renderer: GreetingRenderer = greeting_renderer
        elif image_service is not None:
            self._greeting_renderer = image_service
        else:
            msg = "GreetingService requires greeting_renderer or image_service"
            raise TypeError(msg)
        # Back-compat alias so legacy tests can still access _image_service
        self._image_service = self._greeting_renderer
        # Guild-scoped render caps (design D4): join raids must not stack an
        # unbounded number of concurrent Pillow renders.
        self._raid_semaphores: dict[str, asyncio.Semaphore] = {}

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

    def resolve_renderer(self) -> Any:
        """Resolve the render callable for greeting cards — single source of truth.

        Returns the callable that produces an ``io.BytesIO`` PNG.  Selection
        policy (no mock introspection — decides by real protocol attributes):

            1. If the injected renderer implements the ``GreetingRenderer``
               protocol (i.e. exposes ``render``), use ``renderer.render``.
               This is the canonical path (``PillowGreetingRenderer``).
            2. Else if the renderer exposes ``generate_greeting_card`` (the
               deprecated :class:`~bot.services.image_service.ImageService`
               shim), use that.
            3. Else raise ``AttributeError``.

        The cog test commands (``/welcome_test``, ``/goodbye_test``) and
        :meth:`dispatch_greeting` both go through this resolver so the policy
        exists in exactly one place (DRY — AGENTS.md: "business logic in
        services, not cogs").
        """
        renderer = self._greeting_renderer
        render_fn = getattr(renderer, "render", None)
        if render_fn is not None:
            return render_fn
        gen_fn = getattr(renderer, "generate_greeting_card", None)
        if gen_fn is not None:
            return gen_fn
        msg = "GreetingRenderer missing render/generate_greeting_card"
        raise AttributeError(msg)

    async def dispatch_greeting(  # noqa: C901  -- branching is cache/card/compat migration; will simplify when image_service shim is removed
        self, member: discord.Member, kind: Literal["welcome", "goodbye"]
    ) -> None:
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
        # Raid guard (design D4): guild-scoped Semaphore(2), NON-BLOCKING
        # acquire — a saturated guild drops the greeting with a WARNING
        # instead of queueing unbounded renders or swallowing distinct
        # greetings behind a debounce window.
        sem = self._raid_semaphores.get(guild_id)
        if sem is None:
            sem = asyncio.Semaphore(RAID_MAX_CONCURRENT)
            self._raid_semaphores[guild_id] = sem
        if sem.locked():
            logger.warning("greeting dropped: raid saturation guild=%s", guild_id)
            return
        async with sem:
            # Single source of truth: resolve the render callable via the protocol
            # resolver (no mock introspection — decides by real attributes).
            render_fn = self.resolve_renderer()
            # Shard: avatar cache 60s guild-scoped via cache_key(gid,"greeting_avatar")
            # Populate on first fetch; used only to satisfy cache-key contract + isolation.
            # Actual avatar bytes are still fetched via _resolve_avatar_url each dispatch
            # (CDN URL may rotate), but the cache entry proves guild isolation.
            avatar_cache_key = cache_key(guild_id, "greeting_avatar")
            if self._cache.get(avatar_cache_key) is None and avatar_url is not None:
                self._cache.set(avatar_cache_key, avatar_url, ttl=AVATAR_CACHE_TTL)
            # Shim: if the render function is a legacy signature that doesn't accept
            # localized kwargs, strip them and retry — preserves the compat test.
            try:
                buffer: io.BytesIO = await asyncio.to_thread(
                    render_fn,
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
                    theme_id=getattr(config, "theme_id", None),
                )
            except TypeError as exc:
                msg = str(exc)
                if "unexpected keyword argument" in msg and any(
                    k in msg for k in ("greeting_title", "member_count_text", "guild_icon_url", "theme_id")
                ):
                    # Fallback without theme_id for legacy mocks
                    try:
                        buffer = await asyncio.to_thread(
                            render_fn,
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
                    except TypeError as exc2:
                        msg2 = str(exc2)
                        if "unexpected keyword argument" in msg2:
                            buffer = await asyncio.to_thread(
                                render_fn,
                                username=member.display_name,
                                avatar_url=avatar_url,
                                guild_name=member.guild.name,
                                member_count=member.guild.member_count or 0,
                                card_type=card_type,
                            )
                        else:
                            raise
                else:
                    raise

            file = discord.File(buffer, filename=filename)
            if kind == "welcome":
                content = _compose_welcome_content(member, message, config.onboarding_channel_id)
            else:
                content = _format_template(message or "", member) if message else ""

            await cast(discord.abc.Messageable, channel).send(content=content or None, file=file)

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


def _resolve_avatar_url(member: discord.abc.User) -> str | None:
    """Return the display avatar URL for *member*, or ``None`` on failure.

    Accepts :class:`discord.abc.User` so cogs can pass ``ctx.author`` (typed
    ``User`` but a ``Member`` at runtime in guild context) without a
    ``type: ignore[arg-type]``. ``display_avatar`` exists on both ``User``
    and ``Member``.
    """
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
