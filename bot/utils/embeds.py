"""Embed helpers with consistent styling across all cogs.

Provides factory functions that return pre-styled `discord.Embed` objects
with the NebulosaBot brand palette and dynamic footer icons.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord

from bot.core.i18n import t
from bot.utils.brand import ERROR, INFO, SUCCESS, WARNING

if TYPE_CHECKING:
    from bot.bot import NebulosaBot


# ---------------------------------------------------------------------------
# Asset resolvers
# ---------------------------------------------------------------------------


def bot_avatar_url(bot: NebulosaBot) -> str:
    """Return the bot user's display avatar URL.

    Args:
        bot: The bot instance.

    Returns:
        The URL string for the bot's current avatar.
    """
    if bot.user is None:
        return ""
    return bot.user.display_avatar.url


def guild_footer_icon(
    guild: discord.Guild | None,
    bot: NebulosaBot,
) -> str:
    """Return the guild icon URL, falling back to the bot avatar.

    Args:
        guild: The guild whose icon to prefer, or ``None``.
        bot: The bot instance (used as fallback).

    Returns:
        Guild icon URL if available, otherwise bot avatar URL.
    """
    if guild is not None and guild.icon is not None:
        return guild.icon.url
    return bot_avatar_url(bot)


# ---------------------------------------------------------------------------
# Internal factory
# ---------------------------------------------------------------------------


def _make_embed(
    title: str,
    description: str,
    color: int,
    *,
    timestamp: datetime | None = None,
    guild_id: str | int | None = None,
    bot: NebulosaBot | None = None,
    guild: discord.Guild | None = None,
) -> discord.Embed:
    """Build a consistently styled embed with localized footer.

    Args:
        title: Embed title.
        description: Embed description.
        color: Embed color (int).
        timestamp: Optional timestamp; defaults to now.
        guild_id: Optional guild ID for localized footer text.
        bot: Optional bot instance for footer icon resolution.
        guild: Optional guild for guild-specific footer icon.

    Returns:
        A styled :class:`discord.Embed`.
    """
    now = timestamp or datetime.now(UTC)
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=now,
    )
    footer_text = t(
        guild_id,
        "common.footer",
        timestamp=now.strftime("%Y-%m-%d %H:%M UTC"),
    )
    icon_url: str | None = None
    if bot is not None:
        icon_url = guild_footer_icon(guild, bot)
    embed.set_footer(text=footer_text, icon_url=icon_url)
    return embed


# ---------------------------------------------------------------------------
# Public factories
# ---------------------------------------------------------------------------


def error_embed(
    title: str,
    description: str,
    *,
    guild_id: str | int | None = None,
    bot: NebulosaBot | None = None,
    guild: discord.Guild | None = None,
) -> discord.Embed:
    """Red (ERROR) embed for error messages.

    Args:
        title: Short error heading (e.g. "Permission Denied").
        description: Human-readable explanation.
        guild_id: Optional guild ID for localized footer.
        bot: Optional bot for footer icon.
        guild: Optional guild for footer icon.

    Returns:
        A styled error embed.
    """
    return _make_embed(title, description, ERROR, guild_id=guild_id, bot=bot, guild=guild)


def success_embed(
    title: str,
    description: str,
    *,
    guild_id: str | int | None = None,
    bot: NebulosaBot | None = None,
    guild: discord.Guild | None = None,
) -> discord.Embed:
    """Emerald (SUCCESS) embed for success confirmations.

    Args:
        title: Short success heading (e.g. "Configuration Saved").
        description: What was accomplished.
        guild_id: Optional guild ID for localized footer.
        bot: Optional bot for footer icon.
        guild: Optional guild for footer icon.

    Returns:
        A styled success embed.
    """
    return _make_embed(title, description, SUCCESS, guild_id=guild_id, bot=bot, guild=guild)


def info_embed(
    title: str,
    description: str,
    *,
    guild_id: str | int | None = None,
    bot: NebulosaBot | None = None,
    guild: discord.Guild | None = None,
) -> discord.Embed:
    """Indigo (INFO) embed for informational messages.

    Args:
        title: Informational heading (e.g. "Server Status").
        description: Details and context.
        guild_id: Optional guild ID for localized footer.
        bot: Optional bot for footer icon.
        guild: Optional guild for footer icon.

    Returns:
        A styled info embed.
    """
    return _make_embed(title, description, INFO, guild_id=guild_id, bot=bot, guild=guild)


def warning_embed(
    title: str,
    description: str,
    *,
    guild_id: str | int | None = None,
    bot: NebulosaBot | None = None,
    guild: discord.Guild | None = None,
) -> discord.Embed:
    """Amber (WARNING) embed for warning messages.

    Args:
        title: Warning heading (e.g. "Rate Limited").
        description: What happened and what to do.
        guild_id: Optional guild ID for localized footer.
        bot: Optional bot for footer icon.
        guild: Optional guild for footer icon.

    Returns:
        A styled warning embed.
    """
    return _make_embed(title, description, WARNING, guild_id=guild_id, bot=bot, guild=guild)


def build_ticket_embed(
    ticket: Any,
    *,
    claimed_by: discord.User | discord.Member | None = None,
    guild_id: str | None = None,
    field_definitions: list[dict[str, Any]] | None = None,
    bot: NebulosaBot | None = None,
    guild: discord.Guild | None = None,
) -> discord.Embed:
    """Build the welcome / info embed for a ticket channel."""
    if isinstance(ticket, dict):
        number = ticket.get("ticketNumber", "?")
        status = ticket.get("status", "open")
        author_id = ticket.get("authorId", "unknown")
        subject = ticket.get("subject")
        description_text = ticket.get("description")
        custom_fields = ticket.get("customFields") or {}
    else:
        number = ticket.ticket_number
        status = ticket.status
        author_id = ticket.author_id
        subject = ticket.subject
        description_text = ticket.description
        custom_fields = ticket.custom_fields or {}

    if status == "claimed":
        color = INFO
        title = t(guild_id, "tickets.open.welcome_claimed_title", number=number)
        description = t(guild_id, "tickets.open.welcome_claimed_description")
        if claimed_by is not None:
            description += t(guild_id, "tickets.open.welcome_claimed_by", user=claimed_by.mention)
    else:
        color = SUCCESS
        if subject:
            title = t(guild_id, "tickets.open.welcome_title_with_subject", number=number, subject=subject)
        else:
            title = t(guild_id, "tickets.open.welcome_title", number=number)
        description = t(guild_id, "tickets.open.welcome_description")

    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(UTC))
    embed.add_field(name=t(guild_id, "tickets.open.author_field"), value=f"<@{author_id}>", inline=True)
    if description_text:
        embed.add_field(name=t(guild_id, "tickets.open.details_field"), value=description_text, inline=False)

    # Render custom fields as inline embed fields.
    if custom_fields:
        def_map: dict[str, dict[str, Any]] = {}
        if field_definitions:
            def_map = {d["key"]: d for d in field_definitions}
        for key, value in custom_fields.items():
            if not value:
                continue
            label = def_map.get(key, {}).get("label", key)
            display = str(value)
            if len(display) > 1021:
                display = display[:1021] + "..."
            embed.add_field(name=label, value=display, inline=True)

    footer_kwargs: dict[str, Any] = {"text": t(guild_id, "tickets.open.footer")}
    if bot is not None:
        footer_kwargs["icon_url"] = guild_footer_icon(guild, bot)
    embed.set_footer(**footer_kwargs)
    return embed
