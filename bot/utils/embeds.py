"""Embed helpers with consistent styling across all cogs.

Provides factory functions that return pre-styled `discord.Embed` objects
with the NebulosaBot color scheme and localized footer.
"""

from __future__ import annotations

from datetime import UTC, datetime

import discord

from bot.core.i18n import t

# Brand colors
COLOR_ERROR = 0xE74C3C  # Red
COLOR_SUCCESS = 0x2ECC71  # Green
COLOR_INFO = 0x3498DB  # Blue
COLOR_WARNING = 0xF1C40F  # Yellow

FOOTER_ICON = "https://i.imgur.com/fvE4b0c.png"  # Placeholder — replace with real icon


def _make_embed(
    title: str,
    description: str,
    color: int,
    *,
    timestamp: datetime | None = None,
    guild_id: str | int | None = None,
) -> discord.Embed:
    """Build a consistently styled embed with localized footer.

    Args:
        title: Embed title.
        description: Embed description.
        color: Embed color (int).
        timestamp: Optional timestamp; defaults to now.
        guild_id: Optional guild ID for localized footer text.

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
    embed.set_footer(text=footer_text, icon_url=FOOTER_ICON)
    return embed


def error_embed(
    title: str,
    description: str,
    *,
    guild_id: str | int | None = None,
) -> discord.Embed:
    """Red embed for error messages.

    Args:
        title: Short error heading (e.g. "Permission Denied").
        description: Human-readable explanation.
        guild_id: Optional guild ID for localized footer.

    Returns:
        A styled red embed.
    """
    return _make_embed(title, description, COLOR_ERROR, guild_id=guild_id)


def success_embed(
    title: str,
    description: str,
    *,
    guild_id: str | int | None = None,
) -> discord.Embed:
    """Green embed for success confirmations.

    Args:
        title: Short success heading (e.g. "Configuration Saved").
        description: What was accomplished.
        guild_id: Optional guild ID for localized footer.

    Returns:
        A styled green embed.
    """
    return _make_embed(title, description, COLOR_SUCCESS, guild_id=guild_id)


def info_embed(
    title: str,
    description: str,
    *,
    guild_id: str | int | None = None,
) -> discord.Embed:
    """Blue embed for informational messages.

    Args:
        title: Informational heading (e.g. "Server Status").
        description: Details and context.
        guild_id: Optional guild ID for localized footer.

    Returns:
        A styled blue embed.
    """
    return _make_embed(title, description, COLOR_INFO, guild_id=guild_id)


def warning_embed(
    title: str,
    description: str,
    *,
    guild_id: str | int | None = None,
) -> discord.Embed:
    """Yellow embed for warning messages.

    Args:
        title: Warning heading (e.g. "Rate Limited").
        description: What happened and what to do.
        guild_id: Optional guild ID for localized footer.

    Returns:
        A styled yellow embed.
    """
    return _make_embed(title, description, COLOR_WARNING, guild_id=guild_id)
