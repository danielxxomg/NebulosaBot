"""Permission check decorators for bot commands.

Provides `is_admin()` and `is_mod()` as `@app_commands.check()` decorators
compatible with discord.py hybrid commands.
"""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands

logger = logging.getLogger(__name__)


def is_admin():
    """Require the Administrator permission.

    Usage:
        @commands.hybrid_command(name="sync")
        @is_admin()
        async def sync(self, ctx): ...
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            raise app_commands.NoPrivateMessage(
                "This command can only be used in a server."
            )

        if not interaction.user.guild_permissions.administrator:  # type: ignore[union-attr]
            raise app_commands.MissingPermissions(["administrator"])

        return True

    return app_commands.check(predicate)


def is_mod():
    """Require the configured Moderator role or Administrator permission.

    Check order:
        1. Administrator permission → pass
        2. Guild has a configured mod role AND user has it → pass
        3. Otherwise → deny

    When no guild config is wired yet (Phase 1–2), only administrators pass.

    Usage:
        @commands.hybrid_command(name="warn")
        @is_mod()
        async def warn(self, ctx, member: discord.Member): ...
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            raise app_commands.NoPrivateMessage(
                "This command can only be used in a server."
            )

        # Admin always passes — per spec: admin fallback.
        if interaction.user.guild_permissions.administrator:  # type: ignore[union-attr]
            return True

        mod_role_id = await _resolve_mod_role_id(interaction)

        if mod_role_id is None:
            # No mod role configured — only admins pass (spec: unconfigured mod role).
            raise app_commands.CheckFailure(
                "No moderator role is configured for this server. "
                "Only administrators can use this command."
            )

        if not _user_has_role(interaction.user, mod_role_id):  # type: ignore[arg-type]
            raise app_commands.MissingRole(mod_role_id)

        return True

    return app_commands.check(predicate)


async def _resolve_mod_role_id(interaction: discord.Interaction) -> int | None:
    """Resolve the configured moderator role ID for the guild.

    Tries the following sources in order:
        1. Bot's `_guild_mod_role_cache` dict (set by GuildService in Phase 3+).
        2. Returns None if no source is wired yet (Phase 1–2 safe).
    """
    bot: Any = interaction.client
    guild_id = interaction.guild_id

    # Phase 3+: GuildService populates this cache.
    cache: dict[int, str] | None = getattr(bot, "_guild_mod_role_cache", None)
    if cache is not None and guild_id in cache:
        try:
            return int(cache[guild_id])
        except (ValueError, TypeError):
            logger.warning(
                "Invalid modRoleId in cache for guild %s: %s",
                guild_id,
                cache[guild_id],
            )
            return None

    return None


def _user_has_role(user: discord.Member | discord.User, role_id: int) -> bool:
    """Check whether a user has a specific role by ID."""
    if isinstance(user, discord.User):
        return False  # User is not a Member, has no roles.
    return any(role.id == role_id for role in user.roles)
