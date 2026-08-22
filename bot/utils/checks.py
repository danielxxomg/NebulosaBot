"""Permission check decorators for bot commands.

Provides `is_admin()`, `is_mod()`, and the granular `can()` matrix resolver
compatible with discord.py hybrid commands.
"""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands

logger = logging.getLogger(__name__)

PERMISSIONS: frozenset[str] = frozenset({
    "moderation.warn",
    "moderation.mute",
    "moderation.kick",
    "moderation.ban",
    "tickets.manage",
    "economy.manage",
    "greeting.manage",
})

# ---------------------------------------------------------------------------
# Internal: resolve GuildService without importing bot.bot at top level
# (layering: utils must not import cogs/bot; lazy import via runtime attr).
# ---------------------------------------------------------------------------


def _get_guild_service() -> Any:
    """Resolve the GuildService from the running bot instance if available.

    Checks a module-level override set by tests, then falls back to
    importing the bot instance lazily. Returns None when unavailable.
    """
    # Test override — set by patch("bot.utils.checks._get_guild_service")
    override = getattr(_get_guild_service, "_override", None)
    if override is not None:
        return override
    # Runtime: try to locate bot via current running loop's bot instance
    # Fallback is None — callers must handle None gracefully (deny path).
    return None


def _resolve_member_and_guild_id(ctx: Any) -> tuple[Any, str | None]:
    """Extract (member, guild_id_str) from Context or Interaction."""
    # Context path: ctx.author is the Member, ctx.guild.id is guild id
    # Interaction path: interaction.user is the Member/User, interaction.guild
    guild = getattr(ctx, "guild", None)
    author = getattr(ctx, "author", None) or getattr(ctx, "user", None)
    if guild is None:
        return author, None
    try:
        gid = str(guild.id)  # type: ignore[union-attr]
    except Exception:
        gid = None
    return author, gid


async def _can_core(
    permission: str,
    member: Any,
    guild_id: str | None,
    *,
    bot_ref: Any = None,
) -> bool:
    """Core permission decision — single source for can()/can_member()."""
    # 0. Unknown permission → deny (deny-default for unknowns)
    if permission not in PERMISSIONS:
        return False
    # 1. DM / no guild → deny (no matrix, no modRole)
    if guild_id is None:
        return False
    # 2. Admin always passes — implicit super-permission
    if getattr(getattr(member, "guild_permissions", None), "administrator", False):
        return True

    # 3. Resolve config via GuildService
    service = _get_guild_service()
    # Also try bot_ref.guild_service when patch not active (runtime path)
    if service is None and bot_ref is not None:
        service = getattr(bot_ref, "guild_service", None)
    if service is None:
        # No service available — fall back to modRole cache only for moderation.*
        if not permission.startswith("moderation."):
            return False
        mod_id = None
        if bot_ref is not None:
            try:
                mod_id = _resolve_mod_role_id_from_bot(bot_ref, int(guild_id) if guild_id.isdigit() else None)
            except Exception:
                mod_id = None
        if mod_id is None:
            return False
        return _user_has_role(member, mod_id)

    try:
        config = await service.get_config(guild_id)
    except Exception:
        logger.exception("can() failed to load config for guild %s", guild_id)
        return False

    matrix: dict[str, list[str]] = getattr(config, "permission_matrix", {}) or {}
    # 4. Matrix hit → role intersect
    if permission in matrix:
        role_ids = matrix[permission] or []
        member_role_ids = {str(getattr(r, "id", "")) for r in getattr(member, "roles", [])}
        return any(str(rid) in member_role_ids for rid in role_ids)
    # 5. Moderation fallback to modRoleId when key absent
    if permission.startswith("moderation."):
        mod_role_id_str = getattr(config, "mod_role_id", None)
        if mod_role_id_str is None:
            return False
        try:
            mod_int = int(mod_role_id_str)
        except (ValueError, TypeError):
            return False
        return _user_has_role(member, mod_int)
    # 6. Non-moderation absent → deny
    return False


async def can(permission: str, ctx: Any) -> bool:
    """Granular permission check — bool form for in-cog/ctx call sites.

    See :data:`PERMISSIONS` for the seven valid keys. Returns True only via
    admin pass, matrix role grant, or moderation fallback; otherwise False.
    """
    member, guild_id = _resolve_member_and_guild_id(ctx)
    if member is None:
        return False
    # ctx.bot is available on both Context and Interaction (interaction.client is alias)
    bot_ref = getattr(ctx, "bot", None) or getattr(ctx, "client", None)
    return await _can_core(permission, member, guild_id, bot_ref=bot_ref)


async def can_member(permission: str, member: Any, guild_id: str | None) -> bool:
    """Listener-form permission check — async mirror of :func:`can` for ``on_message`` etc.

    Mirrors :func:`can` for callers that hold a :class:`discord.Member` but no
    ``Context``/``Interaction`` (e.g. read-only listeners, ticket-view
    callbacks). Resolves the bot client from the member's connection state
    (``member._state._get_client()``) so the moderation fallback path can read
    ``bot._guild_mod_role_cache`` at runtime — tests override
    :func:`_get_guild_service` so ``bot_ref`` is not consulted there.
    """
    if guild_id is None:
        return False
    # member may be None in edge cases
    if member is None:
        return False
    # Resolve the bot client from the member's connection state. In discord.py
    # the bot is reachable as ``member._state._get_client()`` (a callable bound
    # in ``Client.__init__``); ``member.bot`` is a *bool* ("is bot account")
    # and MUST NOT be used as the client. Fall back to ``None`` so the deny
    # path stays safe when the member is detached from a live connection.
    bot_ref: Any = None
    state = getattr(member, "_state", None)
    if state is not None:
        get_client = getattr(state, "_get_client", None)
        if callable(get_client):
            try:
                bot_ref = get_client()
            except Exception:
                logger.debug("can_member: member._state._get_client() failed", exc_info=True)
                bot_ref = None
    return await _can_core(
        permission,
        member,
        str(guild_id) if guild_id is not None else None,
        bot_ref=bot_ref,
    )


def can_check(permission: str) -> Any:
    """Decorator factory mirroring is_mod()/is_admin() shape.

    Registers checks on BOTH prefix (commands.check) and slash (app_commands.check).
    """
    import discord as _discord
    from discord.ext import commands as _commands

    async def _app_predicate(interaction: _discord.Interaction) -> bool:
        if not interaction.guild:
            msg = "This command can only be used in a server."
            raise app_commands.NoPrivateMessage(msg)
        if await can(permission, interaction):
            return True
        # Translate deny into CheckFailure for slash path
        msg = f"Missing permission: {permission}"
        raise app_commands.CheckFailure(msg)

    async def _prefix_predicate(ctx: _commands.Context) -> bool:
        if not ctx.guild:
            msg = "This command can only be used in a server."
            raise _commands.NoPrivateMessage(msg)
        if not isinstance(ctx.author, _discord.Member):
            msg = "This command can only be used by guild members."
            raise _commands.CheckFailure(msg)
        if await can(permission, ctx):
            return True
        # For prefix, distinguish mod-role configured? Generic failure keeps spec simple.
        # Tests expect CheckFailure for non-admin/non-granted; MissingRole is for is_mod only.
        # can_check raises CheckFailure for deny.
        msg = f"Missing permission: {permission}"
        raise app_commands.CheckFailure(msg)

    def decorator(func: Any) -> Any:
        return _commands.check(_prefix_predicate)(app_commands.check(_app_predicate)(func))

    decorator.predicate = _app_predicate  # type: ignore[attr-defined]
    decorator.prefix_predicate = _prefix_predicate  # type: ignore[attr-defined]
    return decorator


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
            msg = "This command can only be used in a server."
            raise app_commands.NoPrivateMessage(msg)

        if not interaction.user.guild_permissions.administrator:  # type: ignore[union-attr]
            raise app_commands.MissingPermissions(["administrator"])

        return True

    async def _prefix_predicate(ctx: _commands.Context) -> bool:
        if not ctx.guild:
            msg = "This command can only be used in a server."
            raise _commands.NoPrivateMessage(msg)

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


def is_mod_member(member: discord.Member, bot: Any, guild_id: int) -> bool:
    """Member-based mod gate for listeners (e.g. ``on_message``).

    Synchronous sibling of :func:`is_mod_check` for the ``discord.Message``
    path where no :class:`discord.Interaction` is available. Returns ``True``
    when *member* is an administrator OR holds the guild's configured mod role;
    ``False`` otherwise (including non-members). NEVER raises — listeners must
    not propagate permission-check failures.

    Args:
        member: The message author as a :class:`discord.Member`.
        bot: The bot instance (carries ``_guild_mod_role_cache``).
        guild_id: The guild snowflake (int) the message originated in.
    """
    if getattr(member.guild_permissions, "administrator", False):
        return True
    mod_role_id = _resolve_mod_role_id_from_bot(bot, guild_id)
    if mod_role_id is None:
        return False
    return _user_has_role(member, mod_role_id)


async def _is_mod_via_matrix(interaction_or_ctx: Any) -> bool:
    """Check whether member passes any moderation.* matrix grant (matrix-only, no fallback)."""
    member, guild_id = _resolve_member_and_guild_id(interaction_or_ctx)
    if guild_id is None or member is None:
        return False
    bot_ref = getattr(interaction_or_ctx, "client", None) or getattr(interaction_or_ctx, "bot", None)
    service = _get_guild_service()
    if service is None and bot_ref is not None:
        service = getattr(bot_ref, "guild_service", None)
    if service is None:
        return False
    try:
        cfg = await service.get_config(guild_id)
    except Exception:
        logger.debug("is_mod matrix lookup failed", exc_info=True)
        return False
    matrix = getattr(cfg, "permission_matrix", {}) or {}
    member_role_ids = {str(getattr(r, "id", "")) for r in getattr(member, "roles", [])}
    return any(
        perm in matrix and any(str(rid) in member_role_ids for rid in (matrix[perm] or []))
        for perm in ("moderation.warn", "moderation.mute", "moderation.kick", "moderation.ban")
    )


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
            msg = "This command can only be used in a server."
            raise app_commands.NoPrivateMessage(msg)

        if await is_mod_check(interaction):
            return True
        # Shim: honor moderation.* matrix grants (additive — keeps external outcomes compat)
        if await _is_mod_via_matrix(interaction):
            return True

        # is_mod_check returned False → translate into the precise discord.py
        # exception by consulting the SAME shared role resolver (one source).
        mod_role_id = _resolve_mod_role_id(interaction)

        if mod_role_id is None:
            # No mod role configured — only admins pass (spec: unconfigured mod role).
            msg = "No moderator role is configured for this server. Only administrators can use this command."
            raise app_commands.CheckFailure(msg)

        raise app_commands.MissingRole(mod_role_id)

    async def _prefix_predicate(ctx: _commands.Context) -> bool:
        if not ctx.guild:
            msg = "This command can only be used in a server."
            raise _commands.NoPrivateMessage(msg)

        if not isinstance(ctx.author, _discord.Member):
            msg = "This command can only be used by guild members."
            raise _commands.CheckFailure(msg)

        # Admin always passes.
        if ctx.author.guild_permissions.administrator:
            return True

        if await _is_mod_via_matrix(ctx):
            return True

        mod_role_id = _resolve_mod_role_id_from_bot(ctx.bot, ctx.guild.id)

        if mod_role_id is None:
            msg = "No moderator role is configured for this server. Only administrators can use this command."
            raise _commands.CheckFailure(msg)

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
