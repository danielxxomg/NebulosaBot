"""S2a.1 RED — SetupPanelView persistent non-ephemeral panel.

Ref: setup-panel "Persistent non-ephemeral panel" + "Authorization without new matrix key"
- one non-ephemeral message
- nav edits same message (no duplicate)
- close deletes
- restart routes via static custom_id
- interaction_check denials ephemeral
- admin implicit pass; non-admin blocked by default_perms

TDD: RED must fail while panel framework absent; GREEN after S2a.4/S2a.6/S2a.9.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

# ---------------------------------------------------------------------------
# S2a.4 — SetupPanelView structure
# ---------------------------------------------------------------------------


class TestSetupPanelViewExists:
    """SetupPanelView must exist with timeout=None and static custom_ids."""

    def test_view_class_exists(self) -> None:
        from bot.views.setup_panel import SetupPanelView

        assert SetupPanelView is not None

    def test_timeout_is_none(self) -> None:
        from bot.views.setup_panel import SetupPanelView

        view = SetupPanelView()
        assert view.timeout is None, "Persistent view must have timeout=None"

    def test_static_custom_ids(self) -> None:
        """View must expose static custom_ids setup:nav / setup:refresh / setup:close and pattern setup:{module}:{action}."""
        from bot.views.setup_panel import SetupPanelView

        view = SetupPanelView()
        ids = {getattr(c, "custom_id", None) for c in view.children if hasattr(c, "custom_id")}
        # nav, refresh, close are static; module actions are also static literals like setup:tickets:create_category
        assert "setup:nav" in ids, f"missing setup:nav in {ids}"
        assert "setup:refresh" in ids, f"missing setup:refresh in {ids}"
        assert "setup:close" in ids, f"missing setup:close in {ids}"
        # at least one module action id must follow setup:{module}:{action} pattern
        module_actions = [cid for cid in ids if cid is not None and cid.count(":") == 2 and cid.startswith("setup:")]
        assert module_actions, f"expected at least one setup:{{module}}:{{action}} id, got {ids}"

    def test_bot_add_view_registered(self) -> None:
        """bot.bot.NebulosaBot.setup_hook must register SetupPanelView via add_view."""
        import pathlib

        src = pathlib.Path("bot/bot.py").read_text(encoding="utf-8")
        assert "SetupPanelView" in src, "setup_hook must reference SetupPanelView"
        assert "add_view" in src, "setup_hook must call add_view for persistence"
        # Check that the registration is for SetupPanelView (not only ticket views)
        assert "add_view(SetupPanelView" in src or "add_view( SetupPanelView" in src or "SetupPanelView()" in src

    def test_no_dynamic_custom_ids(self) -> None:
        """All custom_ids must be literal strings, not generated UUIDs or dynamic."""
        from bot.views.setup_panel import SetupPanelView

        view = SetupPanelView()
        for child in view.children:
            cid = getattr(child, "custom_id", None)
            if cid is not None:
                # No UUID-like pattern, no random
                assert cid.startswith("setup:"), f"custom_id must be static setup: namespace, got {cid!r}"
                assert "{" not in cid and "}" not in cid, (
                    f"custom_id must not contain template placeholders, got {cid!r}"
                )


# ---------------------------------------------------------------------------
# Setup command — pure app command, zero params, default_permissions administrator
# ---------------------------------------------------------------------------


class TestSetupCommandIsPureAppCommand:
    """S2a.9: /setup MUST be pure @app_commands.command, zero params, default_permissions administrator."""

    def test_command_is_app_command_not_hybrid(self) -> None:

        # SetupCog.setup_command must be an app_commands.Command (pure) not hybrid
        # hybrid_command exposes .app_command; pure app command is directly app_commands.Command
        import pathlib

        src = pathlib.Path("bot/cogs/setup.py").read_text(encoding="utf-8")
        # Must NOT contain hybrid_command for setup
        assert (
            "hybrid_command" not in src
            or src.count("hybrid_command") == 0
            or "setup" not in src.split("hybrid_command")[0][-200:]
        ), "setup must not use hybrid_command"
        # Must contain app_commands.command
        assert "app_commands.command" in src, "setup must use @app_commands.command"

    def test_zero_params(self) -> None:
        from bot.cogs.setup import SetupCog

        bot = MagicMock()
        cog = SetupCog(bot=bot)
        # For app_commands.Group-less command, the command is registered via cog's __cog_app_commands__
        # Inspect the callback signature: should have only self + interaction
        # Alternatively inspect the command object
        # Find the command registered on the cog
        cmds = [c for c in cog.__cog_app_commands__ if getattr(c, "name", None) == "setup"]
        assert cmds, "SetupCog must expose /setup as app command"
        cmd = cmds[0]
        # app_commands.Command has parameters attribute
        params = getattr(cmd, "parameters", [])
        # Zero params besides self/interaction is expected; but discord.py includes no extra params
        # The command callback should declare zero extra params (pure panel opener)
        assert len(params) == 0, f"/setup must have zero params, got {len(params)}: {params}"
        # Also inspect callback signature
        sig = inspect.signature(cog.setup_command.callback)
        # callback(self, interaction: Interaction) -> 2 params
        assert len(sig.parameters) == 2, (
            f"setup callback must be (self, interaction), got {list(sig.parameters.keys())}"
        )

    def test_default_permissions_administrator(self) -> None:
        import pathlib

        src = pathlib.Path("bot/cogs/setup.py").read_text(encoding="utf-8")
        assert "default_permissions" in src, "setup must carry default_permissions"
        assert "administrator" in src.lower(), "setup default_permissions must gate administrator"

    def test_sends_one_non_ephemeral_message(self) -> None:
        """Invoking /setup must send exactly one non-ephemeral message with SetupPanelView."""
        from bot.cogs.setup import SetupCog

        bot = MagicMock()
        cog = SetupCog(bot=bot)

        # Find command
        cmds = [c for c in cog.__cog_app_commands__ if getattr(c, "name", None) == "setup"]
        assert cmds
        # Use pytest async instead - we will test via async function below
        # This sync test just checks source contract; actual send is tested async

    @pytest.mark.asyncio
    async def test_setup_sends_non_ephemeral_panel(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from bot.cogs.setup import SetupCog

        bot = MagicMock()
        # mock guild_service for render recompute
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=MagicMock(ticket_category_id=None, language="es"))

        cog = SetupCog(bot=bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.is_done.return_value = False
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        interaction.guild = guild
        interaction.guild_id = 123456789
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = True

        await cog.setup_command.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        # MUST be non-ephemeral (ephemeral not True)
        assert kwargs.get("ephemeral") is not True, (
            f"panel must be non-ephemeral, got ephemeral={kwargs.get('ephemeral')}"
        )
        assert kwargs.get("ephemeral") is False or kwargs.get("ephemeral") is None
        # Must include embed and view
        assert "embed" in kwargs
        assert "view" in kwargs
        from bot.views.setup_panel import SetupPanelView

        assert isinstance(kwargs["view"], SetupPanelView)
        # Embed footer must contain nbpanel token
        embed = kwargs["embed"]
        footer_text = getattr(embed.footer, "text", "") or ""
        assert "nbpanel|module=" in footer_text, f"footer must carry nbpanel|module token, got {footer_text!r}"


# ---------------------------------------------------------------------------
# Persistent interactions: nav edits same message, close deletes, restart
# ---------------------------------------------------------------------------


class TestSetupPanelInteractions:
    """Nav edits same message, close deletes, restart via static ids."""

    @pytest.mark.asyncio
    async def test_nav_edits_same_message(self) -> None:
        from bot.views.setup_panel import SetupPanelView

        view = SetupPanelView()
        # Find the Select with custom_id setup:nav
        select = next(c for c in view.children if getattr(c, "custom_id", None) == "setup:nav")
        # Mock interaction for select
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.message = MagicMock()
        interaction.message.embeds = [MagicMock()]
        # Existing footer token
        embed0 = MagicMock()
        embed0.footer.text = "nbpanel|module=tickets"
        interaction.message.embeds[0] = embed0
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123456789
        interaction.guild_id = 123456789
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = True
        interaction.data = {"values": ["tickets"], "custom_id": "setup:nav"}
        # Need to mock guild_service for render recompute
        # Interaction.client is bot
        bot = MagicMock()
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=MagicMock(language="es"))
        bot.db = MagicMock()
        bot.db.get_ticket_categories = AsyncMock(return_value=[])
        interaction.client = bot

        # Invoke callback — discord.py Select callback is at select.callback
        # select.values is derived from interaction.data by production, so no need to set directly
        # The view's select handler is typically view.<method>; find it
        # For SetupPanelView we expect a callback that edits message
        # Call the view's select handler directly if exists, else simulate
        # Find any method that is bound to custom_id setup:nav
        # We will call view's internal handler: for test, assume select callback edits
        await select.callback(interaction)

        # Must edit same message, not send new
        interaction.response.edit_message.assert_awaited_once()
        interaction.response.send_message.assert_not_awaited()
        kwargs = interaction.response.edit_message.call_args.kwargs
        assert "embed" in kwargs or "view" in kwargs

    @pytest.mark.asyncio
    async def test_close_deletes(self) -> None:
        from bot.views.setup_panel import SetupPanelView

        view = SetupPanelView()
        button = next(c for c in view.children if getattr(c, "custom_id", None) == "setup:close")
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.message = MagicMock()
        interaction.message.delete = AsyncMock()
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123456789
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = True
        interaction.client = MagicMock()
        # Call button callback
        await button.callback(interaction)

        interaction.message.delete.assert_awaited_once()


# ---------------------------------------------------------------------------
# interaction_check — admin pass, matrix grant, denial ephemeral
# ---------------------------------------------------------------------------


class TestSetupPanelInteractionCheck:
    """interaction_check must allow admin OR can_member matrix grant, deny → ephemeral."""

    @pytest.mark.asyncio
    async def test_admin_passes(self) -> None:
        from bot.views.setup_panel import SetupPanelView

        view = SetupPanelView()
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = True
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123456789
        interaction.guild_id = 123456789
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        result = await view.interaction_check(interaction)
        assert result is True
        interaction.response.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_admin_without_perm_denied_ephemeral(self) -> None:
        from bot.views.setup_panel import SetupPanelView

        view = SetupPanelView()
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = False
        interaction.user.roles = []
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123456789
        interaction.guild_id = 123456789
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.client = MagicMock()
        # Mock can_member to return False
        with patch("bot.views.setup_panel.can_member", new=AsyncMock(return_value=False)):
            result = await view.interaction_check(interaction)
        assert result is False
        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_matrix_grant_passes(self) -> None:
        from bot.views.setup_panel import SetupPanelView

        view = SetupPanelView()
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = False
        interaction.user.roles = [MagicMock(spec=discord.Role, id=999)]
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123456789
        interaction.guild_id = 123456789
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.client = MagicMock()

        with patch("bot.views.setup_panel.can_member", new=AsyncMock(return_value=True)):
            result = await view.interaction_check(interaction)
        assert result is True
        interaction.response.send_message.assert_not_awaited()
