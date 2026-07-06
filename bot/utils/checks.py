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


async def is_mod_check(interaction: discord.Interaction) -> bool:
    """Bool predicate form of the mod-permission check.

    Returns ``True`` when *interaction* originates in a guild and the user
    is an administrator OR holds the guild's configured moderator role;
    ``False`` otherwise (including DM channels). NEVER raises — this is the
    inline-callable form used directly inside ``discord.ui.button`` callbacks
    where raising from a decorator is unavailable (the design decision in
    ``openspec/changes/ticket-invariant-layer/design.md`` — button gates use
    an inline ``if not await is_mod_check(...): ephemeral deny; return``).

    ``is_mod()`` (the app-command decorator) wraps this predicate and
    converts the ``False`` branch into the appropriate discord.py exception
    (``NoPrivateMessage`` / ``CheckFailure`` / ``MissingRole``).
    """
    if interaction.guild is None:
        return False

    # Admin always passes — per spec: admin fallback.
    if interaction.user.guild_permissions.administrator:  # type: ignore[union-attr]
        return True

    mod_role_id = _resolve_mod_role_id(interaction)
    if mod_role_id is None:
        # No mod role configured — only admins pass (spec: unconfigured mod role).
        return False

    return _user_has_role(interaction.user, mod_role_id)


def is_mod():
    """Require the configured Moderator role or Administrator permission.

    Decorator form of :func:`is_mod_check` for ``@app_commands.check()`` on
    hybrid commands. Raises the appropriate discord.py exception when
    :func:`is_mod_check` returns ``False``; returns ``True`` otherwise.

    Check order (mirrors :func:`is_mod_check`):
        1. DM → ``NoPrivateMessage``
        2. Administrator → pass
        3. Configured mod role and user has it → pass
        4. Mod role unconfigured → ``CheckFailure``
        5. Mod role configured but user lacks it → ``MissingRole``

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

        if interaction.user.guild_permissions.administrator:  # type: ignore[union-attr]
            return True

        mod_role_id = _resolve_mod_role_id(interaction)

        if mod_role_id is None:
            # No mod role configured — only admins pass (spec: unconfigured mod role).
            raise app_commands.CheckFailure(
                "No moderator role is configured for this server. "
                "Only administrators can use this command."
            )

        if not _user_has_role(interaction.user, mod_role_id):
            raise app_commands.MissingRole(mod_role_id)

        return True

    return app_commands.check(predicate)


def _resolve_mod_role_id(interaction: discord.Interaction) -> int | None:
    """Resolve the configured moderator role ID for the guild (non-async).

    Non-async sibling of the previous ``_resolve_mod_role_id`` coroutine —
    inlined by :func:`is_mod_check` since the predicate is called from both
    the decorator (which can await) and inline button callbacks (which also
    await, but the resolution itself is a sync dict lookup, so awaiting is
    unnecessary). Tries the bot's ``_guild_mod_role_cache`` dict and returns
    ``None`` when unconfigured (Phase 1-2 safe).
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
