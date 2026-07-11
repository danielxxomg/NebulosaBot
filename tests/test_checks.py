"""Unit tests for bot.utils.checks — is_admin() and is_mod().

Covers the permission-model spec scenarios:
    - Administrator permission → passes both checks
    - Mod with configured modRoleId → passes is_mod
    - Admin fallback when mod role configured → passes is_mod
    - Regular user without permissions → denied
    - Unconfigured mod role → only admins pass
    - DM invocation → NoPrivateMessage
    - Prefix-path enforcement (harden-command-permissions)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from bot.utils.checks import is_admin, is_mod, is_mod_check

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unwrap_predicate(
    factory: Callable[[], Any],
) -> Callable[..., Any]:
    """Extract the inner predicate function from a check decorator factory.

    For factories that expose a ``.predicate`` attribute (like ``is_admin()``
    after the dual-check enhancement), returns that directly.

    For legacy factories (like ``is_mod()``) that return an
    ``app_commands.check`` wrapper, patches ``app_commands.check`` so it
    becomes a transparent pass-through, returning the raw predicate.
    """
    result = factory()
    # New-style: is_admin() exposes .predicate directly.
    if hasattr(result, "predicate"):
        return result.predicate  # type: ignore[return-value]
    # Legacy: is_mod() returns app_commands.check(predicate).
    with patch("bot.utils.checks.app_commands.check") as mock_check:
        mock_check.side_effect = lambda pred: pred
        return factory()


# ---------------------------------------------------------------------------
# is_admin()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_admin_administrator_passes(mock_interaction: MagicMock) -> None:
    """A user with the Administrator permission MUST pass is_admin()."""
    predicate = _unwrap_predicate(is_admin)

    mock_interaction.guild = MagicMock(spec=discord.Guild)  # not None
    mock_interaction.user.guild_permissions.administrator = True

    result = await predicate(mock_interaction)
    assert result is True


@pytest.mark.asyncio
async def test_is_admin_regular_user_denied(mock_interaction: MagicMock) -> None:
    """A user WITHOUT Administrator MUST raise MissingPermissions."""
    predicate = _unwrap_predicate(is_admin)

    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.user.guild_permissions.administrator = False

    with pytest.raises(app_commands.MissingPermissions) as exc:
        await predicate(mock_interaction)
    assert "administrator" in exc.value.missing_permissions


@pytest.mark.asyncio
async def test_is_admin_dm_raises_no_private_message(
    mock_interaction: MagicMock,
) -> None:
    """is_admin() in a DM channel MUST raise NoPrivateMessage."""
    predicate = _unwrap_predicate(is_admin)

    mock_interaction.guild = None  # DM

    with pytest.raises(app_commands.NoPrivateMessage):
        await predicate(mock_interaction)


# ---------------------------------------------------------------------------
# is_mod() — administrator fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_mod_administrator_passes(mock_interaction: MagicMock) -> None:
    """An admin MUST pass is_mod() regardless of mod-role configuration."""
    predicate = _unwrap_predicate(is_mod)

    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.user.guild_permissions.administrator = True
    # No mod-role cache configured — admin still passes.
    mock_interaction.client._guild_mod_role_cache = {}

    result = await predicate(mock_interaction)
    assert result is True


# ---------------------------------------------------------------------------
# is_mod() — configured mod role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_mod_with_mod_role_passes(mock_interaction: MagicMock) -> None:
    """A non-admin user who has the configured mod role MUST pass is_mod()."""
    predicate = _unwrap_predicate(is_mod)

    mod_role_id = 987654321
    guild_id = 123456789

    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.guild_id = guild_id
    mock_interaction.user.guild_permissions.administrator = False

    # Set up the mod-role cache (populated by GuildService).
    mock_interaction.client._guild_mod_role_cache = {guild_id: str(mod_role_id)}

    # Give the user the moderator role.
    role = MagicMock(spec=discord.Role)
    role.id = mod_role_id
    mock_interaction.user.roles = [role]

    result = await predicate(mock_interaction)
    assert result is True


@pytest.mark.asyncio
async def test_is_mod_regular_user_denied(mock_interaction: MagicMock) -> None:
    """A regular user who is neither admin nor mod MUST raise MissingRole."""
    predicate = _unwrap_predicate(is_mod)

    mod_role_id = 987654321
    guild_id = 123456789

    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.guild_id = guild_id
    mock_interaction.user.guild_permissions.administrator = False

    # Mod role is configured…
    mock_interaction.client._guild_mod_role_cache = {guild_id: str(mod_role_id)}

    # …but the user does NOT have it.
    mock_interaction.user.roles = []

    with pytest.raises(app_commands.MissingRole) as exc:
        await predicate(mock_interaction)
    assert exc.value.missing_role == mod_role_id


# ---------------------------------------------------------------------------
# is_mod() — unconfigured mod role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_mod_unconfigured_mod_role_denied(
    mock_interaction: MagicMock,
) -> None:
    """When no mod role is configured, non-admin users MUST be denied with CheckFailure."""
    predicate = _unwrap_predicate(is_mod)

    guild_id = 123456789

    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.guild_id = guild_id
    mock_interaction.user.guild_permissions.administrator = False

    # No mod-role cache at all.
    mock_interaction.client._guild_mod_role_cache = {}

    with pytest.raises(app_commands.CheckFailure) as exc:
        await predicate(mock_interaction)
    assert "No moderator role is configured" in str(exc.value)


@pytest.mark.asyncio
async def test_is_mod_dm_raises_no_private_message(
    mock_interaction: MagicMock,
) -> None:
    """is_mod() in a DM channel MUST raise NoPrivateMessage."""
    predicate = _unwrap_predicate(is_mod)

    mock_interaction.guild = None  # DM

    with pytest.raises(app_commands.NoPrivateMessage):
        await predicate(mock_interaction)


# ---------------------------------------------------------------------------
# is_mod_check() — bool predicate (callable from button callbacks)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_mod_check_administrator_returns_true(
    mock_interaction: MagicMock,
) -> None:
    """An admin MUST pass is_mod_check() — returns True (no raise)."""
    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.user.guild_permissions.administrator = True
    mock_interaction.client._guild_mod_role_cache = {}

    assert await is_mod_check(mock_interaction) is True


@pytest.mark.asyncio
async def test_is_mod_check_mod_role_returns_true(
    mock_interaction: MagicMock,
) -> None:
    """A non-admin user with the configured mod role MUST pass is_mod_check()."""
    mod_role_id = 987654321
    guild_id = 123456789

    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.guild_id = guild_id
    mock_interaction.user.guild_permissions.administrator = False
    mock_interaction.client._guild_mod_role_cache = {guild_id: str(mod_role_id)}

    role = MagicMock(spec=discord.Role)
    role.id = mod_role_id
    mock_interaction.user.roles = [role]

    assert await is_mod_check(mock_interaction) is True


@pytest.mark.asyncio
async def test_is_mod_check_regular_user_returns_false(
    mock_interaction: MagicMock,
) -> None:
    """A regular user (no admin, no mod role) MUST be denied — returns False."""
    mod_role_id = 987654321
    guild_id = 123456789

    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.guild_id = guild_id
    mock_interaction.user.guild_permissions.administrator = False
    mock_interaction.client._guild_mod_role_cache = {guild_id: str(mod_role_id)}
    mock_interaction.user.roles = []

    assert await is_mod_check(mock_interaction) is False


@pytest.mark.asyncio
async def test_is_mod_check_unconfigured_mod_role_returns_false(
    mock_interaction: MagicMock,
) -> None:
    """When no mod role is configured, a non-admin MUST get False (no raise)."""
    guild_id = 123456789

    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.guild_id = guild_id
    mock_interaction.user.guild_permissions.administrator = False
    mock_interaction.client._guild_mod_role_cache = {}

    assert await is_mod_check(mock_interaction) is False


@pytest.mark.asyncio
async def test_is_mod_check_dm_returns_false(mock_interaction: MagicMock) -> None:
    """In a DM (no guild), is_mod_check() MUST return False (no raise)."""
    mock_interaction.guild = None

    assert await is_mod_check(mock_interaction) is False


@pytest.mark.asyncio
async def test_is_mod_wraps_is_mod_check_for_admin(
    mock_interaction: MagicMock,
) -> None:
    """is_mod() decorator MUST delegate to is_mod_check() — admin still passes."""
    predicate = _unwrap_predicate(is_mod)

    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.user.guild_permissions.administrator = True
    mock_interaction.client._guild_mod_role_cache = {}

    # is_mod() raises on failure; admin → True (no raise).
    assert await predicate(mock_interaction) is True


@pytest.mark.asyncio
async def test_is_mod_wraps_is_mod_check_for_denied_user(
    mock_interaction: MagicMock,
) -> None:
    """is_mod() decorator MUST raise when is_mod_check() would return False."""
    predicate = _unwrap_predicate(is_mod)

    guild_id = 123456789
    mod_role_id = 987654321
    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.guild_id = guild_id
    mock_interaction.user.guild_permissions.administrator = False
    mock_interaction.client._guild_mod_role_cache = {guild_id: str(mod_role_id)}
    mock_interaction.user.roles = []

    # is_mod() raises (CheckFailure/MissingRole) when the predicate is False.
    with pytest.raises((app_commands.CheckFailure, app_commands.MissingRole)):
        await predicate(mock_interaction)


@pytest.mark.asyncio
async def test_is_mod_predicate_delegates_to_is_mod_check(
    mock_interaction: MagicMock,
) -> None:
    """CRITICAL 6: is_mod()'s predicate MUST delegate the admin-OR-mod decision
    to ``is_mod_check`` (DRY) rather than re-implementing the role logic.

    Patching the module-level ``is_mod_check`` and asserting it was awaited
    proves the delegation — the decorator reuses the inline predicate's
    decision logic instead of duplicating it. The existing
    ``test_is_mod_wraps_is_mod_check_*`` behavior tests assert the observable
    outcome; this test asserts the structural (no-duplication) contract.
    """
    predicate = _unwrap_predicate(is_mod)

    guild_id = 123456789
    mod_role_id = 555555
    mock_interaction.guild = MagicMock(spec=discord.Guild)
    mock_interaction.guild_id = guild_id
    mock_interaction.user.guild_permissions.administrator = False
    mod_role = MagicMock(spec=discord.Role)
    mod_role.id = mod_role_id
    mock_interaction.user.roles = [mod_role]
    mock_interaction.client._guild_mod_role_cache = {guild_id: str(mod_role_id)}

    with patch("bot.utils.checks.is_mod_check", new=AsyncMock(return_value=True)) as spy:
        result = await predicate(mock_interaction)

    assert result is True
    spy.assert_awaited_once_with(mock_interaction)


# ---------------------------------------------------------------------------
# is_mod() — prefix path (harden-command-permissions)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_mod_prefix_predicate_exists() -> None:
    """is_mod() MUST expose a prefix_predicate attribute (like is_admin())."""
    decorator = is_mod()
    assert hasattr(decorator, "prefix_predicate"), "is_mod() must expose .prefix_predicate"
    assert callable(decorator.prefix_predicate), "prefix_predicate must be callable"


@pytest.mark.asyncio
async def test_is_mod_prefix_admin_passes(mock_guild: MagicMock, mock_admin_member: MagicMock) -> None:
    """An administrator MUST pass the prefix predicate even with no mod role configured."""
    prefix_predicate = is_mod().prefix_predicate

    ctx = MagicMock(spec=commands.Context)
    ctx.guild = mock_guild
    ctx.author = mock_admin_member
    ctx.bot = MagicMock()
    ctx.bot._guild_mod_role_cache = {}

    result = await prefix_predicate(ctx)
    assert result is True


@pytest.mark.asyncio
async def test_is_mod_prefix_admin_passes_with_configured_role(
    mock_guild: MagicMock, mock_admin_member: MagicMock
) -> None:
    """An administrator MUST pass the prefix predicate when a mod role IS configured."""
    prefix_predicate = is_mod().prefix_predicate

    ctx = MagicMock(spec=commands.Context)
    ctx.guild = mock_guild
    ctx.author = mock_admin_member
    ctx.bot = MagicMock()
    ctx.bot._guild_mod_role_cache = {mock_guild.id: "987654321"}

    result = await prefix_predicate(ctx)
    assert result is True


@pytest.mark.asyncio
async def test_is_mod_prefix_non_member_raises_check_failure(mock_guild: MagicMock) -> None:
    """A non-Member author (e.g. User) MUST raise commands.CheckFailure on prefix path."""
    prefix_predicate = is_mod().prefix_predicate

    non_member = MagicMock()
    non_member.__class__ = discord.User
    non_member.guild_permissions.administrator = False

    ctx = MagicMock(spec=commands.Context)
    ctx.guild = mock_guild
    ctx.author = non_member
    ctx.bot = MagicMock()
    ctx.bot._guild_mod_role_cache = {mock_guild.id: "987654321"}

    with pytest.raises(commands.CheckFailure) as exc:
        await prefix_predicate(ctx)
    assert "guild members" in str(exc.value)


@pytest.mark.asyncio
async def test_is_mod_prefix_malformed_cache_denies(
    mock_guild: MagicMock, mock_member: MagicMock
) -> None:
    """Malformed mod role cache values MUST deny-by-default (CheckFailure)."""
    prefix_predicate = is_mod().prefix_predicate

    ctx = MagicMock(spec=commands.Context)
    ctx.guild = mock_guild
    ctx.author = mock_member
    ctx.bot = MagicMock()
    ctx.bot._guild_mod_role_cache = {mock_guild.id: "not-a-number"}

    with pytest.raises(commands.CheckFailure):
        await prefix_predicate(ctx)


def test_user_has_role_returns_false_for_user() -> None:
    """_user_has_role MUST return False for a discord.User (no roles)."""
    from bot.utils.checks import _user_has_role

    user = MagicMock()
    user.__class__ = discord.User
    assert _user_has_role(user, 123) is False


@pytest.mark.asyncio
async def test_is_mod_prefix_mod_role_passes(mock_guild: MagicMock, mock_mod_member: MagicMock) -> None:
    """A user with the configured mod role MUST pass the prefix predicate."""
    prefix_predicate = is_mod().prefix_predicate

    mod_role_id = 987654321
    guild_id = mock_guild.id

    ctx = MagicMock(spec=commands.Context)
    ctx.guild = mock_guild
    ctx.author = mock_mod_member
    ctx.bot = MagicMock()
    ctx.bot._guild_mod_role_cache = {guild_id: str(mod_role_id)}

    result = await prefix_predicate(ctx)
    assert result is True


@pytest.mark.asyncio
async def test_is_mod_prefix_regular_user_raises_missing_role(
    mock_guild: MagicMock, mock_member: MagicMock
) -> None:
    """A user without the mod role MUST raise commands.MissingRole when mod role is configured."""
    prefix_predicate = is_mod().prefix_predicate

    mod_role_id = 987654321
    guild_id = mock_guild.id

    ctx = MagicMock(spec=commands.Context)
    ctx.guild = mock_guild
    ctx.author = mock_member
    ctx.bot = MagicMock()
    ctx.bot._guild_mod_role_cache = {guild_id: str(mod_role_id)}

    with pytest.raises(commands.MissingRole):
        await prefix_predicate(ctx)


@pytest.mark.asyncio
async def test_is_mod_prefix_dm_raises_no_private_message() -> None:
    """In a DM (no guild), the prefix predicate MUST raise commands.NoPrivateMessage."""
    prefix_predicate = is_mod().prefix_predicate

    ctx = MagicMock(spec=commands.Context)
    ctx.guild = None

    with pytest.raises(commands.NoPrivateMessage):
        await prefix_predicate(ctx)


@pytest.mark.asyncio
async def test_is_mod_prefix_unconfigured_raises_check_failure(
    mock_guild: MagicMock, mock_member: MagicMock
) -> None:
    """When no mod role is configured and user is not admin, MUST raise commands.CheckFailure."""
    prefix_predicate = is_mod().prefix_predicate

    ctx = MagicMock(spec=commands.Context)
    ctx.guild = mock_guild
    ctx.author = mock_member
    ctx.bot = MagicMock()
    ctx.bot._guild_mod_role_cache = {}

    with pytest.raises(commands.CheckFailure) as exc:
        await prefix_predicate(ctx)
    assert "No moderator role is configured" in str(exc.value)


# ---------------------------------------------------------------------------
# is_mod() — dual registration integration (JD-B-004)
# ---------------------------------------------------------------------------


def test_is_mod_dual_registration() -> None:
    """A hybrid command decorated with @is_mod() MUST have BOTH prefix and slash checks.

    Integration wiring test: instantiate a real hybrid command, apply @is_mod(),
    and assert cmd.checks (prefix) is non-empty AND app_command.checks (slash)
    is non-empty.
    """

    @is_mod()
    @commands.hybrid_command(name="test_dual")
    async def test_cmd(self, ctx):  # pragma: no cover
        pass

    # Prefix path checks (commands.check)
    assert len(test_cmd.checks) > 0, "prefix checks must be non-empty"
    # Slash path checks (app_commands.check)
    assert len(test_cmd.app_command.checks) > 0, "slash checks must be non-empty"
