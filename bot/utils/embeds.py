"""Embed helpers with consistent styling across all cogs.

Provides factory functions that return pre-styled `discord.Embed` objects
with the NebulosaBot color scheme and footer.
"""

from __future__ import annotations

from datetime import UTC, datetime

import discord

# Brand colors
COLOR_ERROR = 0xE74C3C  # Red
COLOR_SUCCESS = 0x2ECC71  # Green
COLOR_INFO = 0x3498DB  # Blue
COLOR_WARNING = 0xF1C40F  # Yellow

FOOTER_TEXT = "NebulosaBot • {timestamp}"
FOOTER_ICON = "https://i.imgur.com/fvE4b0c.png"  # Placeholder — replace with real icon


def _make_embed(
    title: str,
    description: str,
    color: int,
    *,
    timestamp: datetime | None = None,
) -> discord.Embed:
    """Build a consistently styled embed."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=timestamp or datetime.now(UTC),
    )
    embed.set_footer(
        text=FOOTER_TEXT.format(
            timestamp=(timestamp or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC"),
        ),
        icon_url=FOOTER_ICON,
    )
    return embed


def error_embed(title: str, description: str) -> discord.Embed:
    """Red embed for error messages.

    Args:
        title: Short error heading (e.g. "Permission Denied").
        description: Human-readable explanation.

    Returns:
        A styled red embed.
    """
    return _make_embed(title, description, COLOR_ERROR)


def success_embed(title: str, description: str) -> discord.Embed:
    """Green embed for success confirmations.

    Args:
        title: Short success heading (e.g. "Configuration Saved").
        description: What was accomplished.

    Returns:
        A styled green embed.
    """
    return _make_embed(title, description, COLOR_SUCCESS)


def info_embed(title: str, description: str) -> discord.Embed:
    """Blue embed for informational messages.

    Args:
        title: Informational heading (e.g. "Server Status").
        description: Details and context.

    Returns:
        A styled blue embed.
    """
    return _make_embed(title, description, COLOR_INFO)


def warning_embed(title: str, description: str) -> discord.Embed:
    """Yellow embed for warning messages.

    Args:
        title: Warning heading (e.g. "Rate Limited").
        description: What happened and what to do.

    Returns:
        A styled yellow embed.
    """
    return _make_embed(title, description, COLOR_WARNING)
