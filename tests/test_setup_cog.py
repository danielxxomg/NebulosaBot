"""Unit tests for bot.cogs.setup.SetupCog.

Covers the /setup hybrid command:
    - Permission gate: non-admin rejected
    - Required param: ticket_category (CategoryChannel) saved
    - Optional params: mod_role, log_channel, language saved when provided
    - Partial update: omitted optional params preserve existing values
    - i18n: success response uses t() with correct keys

TDD cycle: RED → GREEN — tests specify expected behavior before implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.cogs.setup import SetupCog
from bot.models.guild import GuildConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def setup_bot() -> MagicMock:
    """Return a mock NebulosaBot for setup tests."""
    bot = MagicMock()
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock()
    bot.guild_service.save_config = AsyncMock()
    bot._guild_mod_role_cache = {}
    return bot


@pytest.fixture
def setup_cog(setup_bot: MagicMock) -> SetupCog:
    """Return a SetupCog wired to the mock bot."""
    return SetupCog(bot=setup_bot)


@pytest.fixture
def admin_ctx(setup_bot: MagicMock) -> MagicMock:
    """Return a mock Context for an admin user in a guild."""
    ctx = MagicMock()
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    ctx.guild = guild
    ctx.guild_id = guild.id

    author = MagicMock(spec=discord.Member)
    author.guild_permissions.administrator = True
    author.id = 111111111
    ctx.author = author

    ctx.send = AsyncMock()
    ctx.interaction = MagicMock()  # slash invocation
    ctx.bot = setup_bot
    return ctx


@pytest.fixture
def ticket_category_channel() -> MagicMock:
    """Return a mock CategoryChannel."""
    ch = MagicMock(spec=discord.CategoryChannel)
    ch.id = 500000000
    ch.name = "Tickets"
    return ch


@pytest.fixture
def mod_role() -> MagicMock:
    """Return a mock Role."""
    role = MagicMock(spec=discord.Role)
    role.id = 987654321
    role.name = "Moderator"
    return role


@pytest.fixture
def log_channel() -> MagicMock:
    """Return a mock TextChannel."""
    ch = MagicMock(spec=discord.TextChannel)
    ch.id = 777777777
    ch.name = "logs"
    return ch


# ---------------------------------------------------------------------------
# 1.1 — Permission gate
# ---------------------------------------------------------------------------


class TestSetupPermissionGate:
    """Tests for @is_admin() gate on /setup."""

    def test_setup_command_has_admin_check(self, setup_cog: SetupCog) -> None:
        """/setup MUST be gated by @is_admin() check."""
        cmd = setup_cog.setup_command
        assert cmd is not None, "/setup command must exist"
        # hybrid_command with @is_admin() registers checks on the command
        has_check = bool(cmd.checks) or (hasattr(cmd, "app_command") and bool(cmd.app_command.checks))  # type: ignore[union-attr]
        assert has_check, "/setup MUST be gated by @is_admin()"

    def test_setup_command_prefix_path_has_permission_check(self, setup_cog: SetupCog) -> None:
        """/setup prefix path MUST be gated by a permission check (not only app_command).

        CRITICAL 1 fix: hybrid commands with @app_commands.check() only gate the
        slash path. A @commands.has_permissions() decorator on the command itself
        gates the prefix path too.
        """
        cmd = setup_cog.setup_command
        # The command MUST have at least one check registered at the command level
        # (not only on app_command). commands.has_permissions registers on cmd.checks.
        assert cmd.checks, (
            "/setup prefix path is NOT gated — cmd.checks is empty. "
            "Add @commands.has_permissions(administrator=True) to gate both slash and prefix paths."
        )


# ---------------------------------------------------------------------------
# 1.2 — Required param + save
# ---------------------------------------------------------------------------


class TestSetupRequiredParam:
    """Tests for /setup with required ticket_category param."""

    async def test_save_with_required_only(
        self,
        setup_cog: SetupCog,
        admin_ctx: MagicMock,
        setup_bot: MagicMock,
        ticket_category_channel: MagicMock,
    ) -> None:
        """Admin invokes /setup with ticket_category only → save_config called.

        Optional fields (mod_role, log_channel, language) are None → existing
        values preserved.
        """
        existing_config = GuildConfig(
            id="123456789",
            prefix="nb!",
            language="es",
            mod_role_id="111111111",
            log_channel_id="222222222",
        )
        setup_bot.guild_service.get_config = AsyncMock(return_value=existing_config)

        # Patch t() to return a predictable string (i18n keys may not exist yet).
        with patch("bot.cogs.setup.t", return_value="Setup complete"):
            await setup_cog.setup_command.callback(
                setup_cog,
                admin_ctx,
                ticket_category=ticket_category_channel,
            )

        # save_config called with updated GuildConfig.
        setup_bot.guild_service.save_config.assert_awaited_once()
        saved_config = setup_bot.guild_service.save_config.call_args.args[0]
        assert isinstance(saved_config, GuildConfig)
        assert saved_config.ticket_category_id == str(ticket_category_channel.id)
        # Optional fields preserved from existing config.
        assert saved_config.mod_role_id == "111111111"
        assert saved_config.log_channel_id == "222222222"

    async def test_save_with_all_params(
        self,
        setup_cog: SetupCog,
        admin_ctx: MagicMock,
        setup_bot: MagicMock,
        ticket_category_channel: MagicMock,
        mod_role: MagicMock,
        log_channel: MagicMock,
    ) -> None:
        """Admin invokes /setup with all params → all four fields saved."""
        existing_config = GuildConfig(id="123456789")
        setup_bot.guild_service.get_config = AsyncMock(return_value=existing_config)

        with patch("bot.cogs.setup.t", return_value="Setup complete"):
            await setup_cog.setup_command.callback(
                setup_cog,
                admin_ctx,
                ticket_category=ticket_category_channel,
                mod_role=mod_role,
                log_channel=log_channel,
                language="en",
            )

        setup_bot.guild_service.save_config.assert_awaited_once()
        saved_config = setup_bot.guild_service.save_config.call_args.args[0]
        assert saved_config.ticket_category_id == str(ticket_category_channel.id)
        assert saved_config.mod_role_id == str(mod_role.id)
        assert saved_config.log_channel_id == str(log_channel.id)
        assert saved_config.language == "en"


# ---------------------------------------------------------------------------
# 1.3 — Partial update preserves existing
# ---------------------------------------------------------------------------


class TestSetupPartialUpdate:
    """Tests for partial /setup preserving existing values."""

    async def test_partial_update_preserves_existing(
        self,
        setup_cog: SetupCog,
        admin_ctx: MagicMock,
        setup_bot: MagicMock,
        ticket_category_channel: MagicMock,
    ) -> None:
        """Guild has mod_role_id=111, log_channel_id=222; invoke /setup with
        ticket_category + language:en → mod_role_id and log_channel_id unchanged.
        """
        existing_config = GuildConfig(
            id="123456789",
            prefix="nb!",
            language="es",
            mod_role_id="111111111",
            log_channel_id="222222222",
        )
        setup_bot.guild_service.get_config = AsyncMock(return_value=existing_config)

        with patch("bot.cogs.setup.t", return_value="Setup complete"):
            await setup_cog.setup_command.callback(
                setup_cog,
                admin_ctx,
                ticket_category=ticket_category_channel,
                language="en",
            )

        setup_bot.guild_service.save_config.assert_awaited_once()
        saved_config = setup_bot.guild_service.save_config.call_args.args[0]
        # ticket_category updated, language updated.
        assert saved_config.ticket_category_id == str(ticket_category_channel.id)
        assert saved_config.language == "en"
        # mod_role_id and log_channel_id PRESERVED from existing.
        assert saved_config.mod_role_id == "111111111"
        assert saved_config.log_channel_id == "222222222"


# ---------------------------------------------------------------------------
# 1.4 — i18n response
# ---------------------------------------------------------------------------


class TestSetupI18nResponse:
    """Tests for /setup using t() for response strings."""

    async def test_success_embed_uses_t(
        self,
        setup_cog: SetupCog,
        admin_ctx: MagicMock,
        setup_bot: MagicMock,
        ticket_category_channel: MagicMock,
    ) -> None:
        """Success embed title and description MUST use t() with setup keys."""
        existing_config = GuildConfig(id="123456789")
        setup_bot.guild_service.get_config = AsyncMock(return_value=existing_config)

        with patch("bot.cogs.setup.t", return_value="translated") as mock_t:
            await setup_cog.setup_command.callback(
                setup_cog,
                admin_ctx,
                ticket_category=ticket_category_channel,
            )

        # t() called with guild_id and setup.success.* keys.
        calls = mock_t.call_args_list
        t_keys = [call.args[1] for call in calls]
        assert any("setup.success" in key for key in t_keys), f"Expected setup.success.* i18n key, got: {t_keys}"

    async def test_success_response_is_ephemeral_for_slash(
        self,
        setup_cog: SetupCog,
        admin_ctx: MagicMock,
        setup_bot: MagicMock,
        ticket_category_channel: MagicMock,
    ) -> None:
        """Slash invocation → success embed sent ephemerally."""
        existing_config = GuildConfig(id="123456789")
        setup_bot.guild_service.get_config = AsyncMock(return_value=existing_config)
        # ctx.interaction is not None → slash invocation.
        admin_ctx.interaction = MagicMock()

        with patch("bot.cogs.setup.t", return_value="Setup complete"):
            await setup_cog.setup_command.callback(
                setup_cog,
                admin_ctx,
                ticket_category=ticket_category_channel,
            )

        admin_ctx.send.assert_awaited_once()
        call_kwargs = admin_ctx.send.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# CRITICAL 5 — Spec scenario coverage tests
# ---------------------------------------------------------------------------


class TestSetupSpecScenarios:
    """Tests covering spec scenarios not yet exercised: required param,
    language validation, and i18n response language switching."""

    def test_ticket_category_param_is_required(self, setup_cog: SetupCog) -> None:
        """ticket_category MUST be a required parameter (no default value).

        Spec: "WHEN /setup is invoked without ticket_category THEN the command
        is rejected by Discord's parameter validation."
        Discord enforces this via the parameter having no default — verify the
        command signature exposes it as required.
        """
        import inspect

        sig = inspect.signature(setup_cog.setup_command.callback)
        param = sig.parameters["ticket_category"]
        # A required param has no default value (param.default is inspect.Parameter.empty).
        assert param.default is inspect.Parameter.empty, (
            f"ticket_category must be required (no default). Got default={param.default!r}"
        )

    def test_language_param_rejects_invalid_choice(self, setup_cog: SetupCog) -> None:
        """language param MUST only accept 'es' or 'en'.

        Spec: "WHEN /setup ticket_category:#Tickets language:xx is invoked
        THEN the command is rejected (invalid choice)."
        Discord enforces this via Literal['es', 'en'] type annotation — verify
        the annotation constrains choices.
        """
        import typing

        cmd = setup_cog.setup_command
        # Resolve the language param's type annotation from the callback.
        annotations = typing.get_type_hints(cmd.callback, include_extras=True)
        lang_type = annotations.get("language")
        assert lang_type is not None, "language param must have a type annotation"

        # Optional[Literal['es', 'en']] is Union[Literal['es', 'en'], NoneType].
        # Get the inner Literal args.
        origin = getattr(lang_type, "__origin__", None)
        if origin is typing.Union:
            # Extract Literal from Union[..., None]
            args = [a for a in lang_type.__args__ if a is not type(None)]
            lang_type = args[0] if args else lang_type

        literal_args = getattr(lang_type, "__args__", None)
        assert literal_args is not None, f"language must be Literal type, got {lang_type}"
        assert set(literal_args) == {"es", "en"}, (
            f"language choices must be exactly {{'es', 'en'}}, got {set(literal_args)}"
        )

    async def test_setup_response_differs_by_guild_language(
        self,
        setup_cog: SetupCog,
        admin_ctx: MagicMock,
        setup_bot: MagicMock,
        ticket_category_channel: MagicMock,
    ) -> None:
        """Success embed text MUST differ between es and en guilds.

        Spec: "GIVEN a guild configured with language=en WHEN /setup completes
        successfully THEN the confirmation embed text is in English" (and vice
        versa for es). The implementation calls t() with the guild_id — verify
        t() is invoked with the correct guild_id so the i18n system resolves
        the right locale.
        """
        existing_config = GuildConfig(id="123456789", language="en")
        setup_bot.guild_service.get_config = AsyncMock(return_value=existing_config)

        with patch("bot.cogs.setup.t", return_value="translated") as mock_t:
            await setup_cog.setup_command.callback(
                setup_cog,
                admin_ctx,
                ticket_category=ticket_category_channel,
            )

        # t() must be called with the guild_id (not None) so the guild
        # language (en) is used, not the default (es).
        for call in mock_t.call_args_list:
            guild_id_arg = call.args[0]
            assert guild_id_arg == "123456789", (
                f"t() must receive guild_id='123456789' to resolve the guild's language. Got guild_id={guild_id_arg!r}"
            )
