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


def is_admin() -> Any:
    """Require the Administrator permission.

    Registers checks on BOTH the slash path (``app_commands.check``) and the
    prefix path (``commands.check``) so hybrid commands are fully gated without
    needing a separate ``@commands.has_permissions(administrator=True)``.

    Usage:
        @commands.hybrid_command(name="sync")
        @is_admin()
        async def sync(self, ctx): ...
    """
    import discord as _discord
    from discord.ext import commands as _commands

    async def _app_predicate(interaction: _discord.Interaction) -> bool:
        if not interaction.guild:
            raise app_commands.NoPrivateMessage("This command can only be used in a server.")

        if not interaction.user.guild_permissions.administrator:  # type: ignore[union-attr]
            raise app_commands.MissingPermissions(["administrator"])

        return True

    async def _prefix_predicate(ctx: _commands.Context) -> bool:  # type: ignore[type-arg]
        if not ctx.guild:
            raise _commands.NoPrivateMessage("This command can only be used in a server.")

        if not isinstance(ctx.author, _discord.Member) or not ctx.author.guild_permissions.administrator:
            raise _commands.MissingPermissions(["administrator"])

        return True

    def decorator(func: Any) -> Any:
        return _commands.check(_prefix_predicate)(app_commands.check(_app_predicate)(func))

    # Expose predicates for testing.
    decorator.predicate = _app_predicate  # type: ignore[attr-defined]
    decorator.prefix_predicate = _prefix_predicate  # type: ignore[attr-defined]
    return decorator


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


def is_mod() -> Any:
    """Require the configured Moderator role or Administrator permission.

    Decorator form of :func:`is_mod_check` for ``@app_commands.check()`` on
    hybrid commands. The admin-OR-mod-role DECISION is delegated to
    :func:`is_mod_check` (DRY — single source of truth for the permission
    logic shared with the inline button-callback predicate). The decorator
    translates ``is_mod_check``'s ``False`` into the appropriate discord.py
    exception (``NoPrivateMessage`` / ``CheckFailure`` / ``MissingRole``).

    Registers checks on BOTH the slash path (``app_commands.check``) and the
    prefix path (``commands.check``) so hybrid commands are fully gated without
    needing a separate ``@commands.has_roles(...)``.

    Check order (mirrors :func:`is_mod_check`):
        1. DM → ``NoPrivateMessage``
        2. Administrator → pass (via is_mod_check)
        3. Configured mod role and user has it → pass (via is_mod_check)
        4. Mod role unconfigured → ``CheckFailure``
        5. Mod role configured but user lacks it → ``MissingRole``

    Usage:
        @commands.hybrid_command(name="warn")
        @is_mod()
        async def warn(self, ctx, member: discord.Member): ...
    """
    import discord as _discord
    from discord.ext import commands as _commands

    async def predicate(interaction: _discord.Interaction) -> bool:
        # DM guard surfaces the specific NoPrivateMessage exception —
        # is_mod_check only returns False for DMs (never raises).
        if not interaction.guild:
            raise app_commands.NoPrivateMessage("This command can only be used in a server.")

        if await is_mod_check(interaction):
            return True

        # is_mod_check returned False → translate into the precise discord.py
        # exception by consulting the SAME shared role resolver (one source).
        mod_role_id = _resolve_mod_role_id(interaction)

        if mod_role_id is None:
            # No mod role configured — only admins pass (spec: unconfigured mod role).
            raise app_commands.CheckFailure(
                "No moderator role is configured for this server. Only administrators can use this command."
            )

        raise app_commands.MissingRole(mod_role_id)

    async def _prefix_predicate(ctx: _commands.Context) -> bool:  # type: ignore[type-arg]
        if not ctx.guild:
            raise _commands.NoPrivateMessage("This command can only be used in a server.")

        if not isinstance(ctx.author, _discord.Member):
            raise _commands.CheckFailure(
                "This command can only be used by guild members."
            )

        # Admin always passes.
        if ctx.author.guild_permissions.administrator:
            return True

        mod_role_id = _resolve_mod_role_id_from_bot(ctx.bot, ctx.guild.id)

        if mod_role_id is None:
            raise _commands.CheckFailure(
                "No moderator role is configured for this server. Only administrators can use this command."
            )

        if _user_has_role(ctx.author, mod_role_id):
            return True

        raise _commands.MissingRole(mod_role_id)

    def decorator(func: Any) -> Any:
        return _commands.check(_prefix_predicate)(app_commands.check(predicate)(func))

    # Expose predicates for testing, matching is_admin().
    decorator.predicate = predicate  # type: ignore[attr-defined]
    decorator.prefix_predicate = _prefix_predicate  # type: ignore[attr-defined]
    return decorator


def _resolve_mod_role_id(interaction: discord.Interaction) -> int | None:
    """Resolve the configured moderator role ID for the guild (non-async).

    Non-async sibling of the previous ``_resolve_mod_role_id`` coroutine —
    inlined by :func:`is_mod_check` since the predicate is called from both
    the decorator (which can await) and inline button callbacks (which also
    await, but the resolution itself is a sync dict lookup, so awaiting is
    unnecessary). Tries the bot's ``_guild_mod_role_cache`` dict and returns
    ``None`` when unconfigured (Phase 1-2 safe).
    """
    return _resolve_mod_role_id_from_bot(interaction.client, interaction.guild_id)


def _resolve_mod_role_id_from_bot(bot: Any, guild_id: int | None) -> int | None:
    """Shared resolver: look up the configured moderator role ID from cache.

    Used by both the interaction-based path (``_resolve_mod_role_id``) and the
    context-based prefix path. Reads ``bot._guild_mod_role_cache`` and returns
    ``None`` when unconfigured or the cached value is malformed.
    """
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
