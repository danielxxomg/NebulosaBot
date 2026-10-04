"""Tests for Phase 3 Tab Bar Layout in SetupPanelView (Pestañas por Botonera Directa).

Validates:
- Row 0 contains 5 tab buttons (tickets, welcome, goodbye, log, language).
- Active tab button has ButtonStyle.primary and disabled=True; inactive buttons have ButtonStyle.secondary and disabled=False.
- Row 1 contains fixed refresh (setup:refresh) and close (setup:close) buttons.
- Contextual components across all 5 tabs (Rows 2-4).
- Max 5 action rows across all tab views (Discord constraint).
- Tab switching reconstructs SetupPanelView with new current_module and edits message.
- Channel selection and clearing for log, welcome, and goodbye tabs.
- Language switching (set_es, set_en).
- Interaction permission checks (matrix gating tickets.manage / greeting.manage, admin bypass).
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.bot import NebulosaBot
from bot.config import BotConfig
from bot.core.i18n import load_locales, set_guild_language
from bot.views.setup_modules._template_picker import handle_template_select_flow
from bot.views.setup_modules.goodbye import GoodbyeSetupModule
from bot.views.setup_modules.language import LanguageSetupModule
from bot.views.setup_modules.log import LogSetupModule
from bot.views.setup_modules.welcome import WelcomeSetupModule
from bot.views.setup_panel import TAB_MODULES, SetupPanelView, _build_embed, _parse_module_from_footer

# Load locales for test assertions
load_locales()


def _get_cid(item: discord.ui.Item) -> str | None:
    return getattr(item, "custom_id", None)


def _get_row(item: discord.ui.Item) -> int | None:
    return getattr(item, "row", None)


class TestSetupTabBarLayout:
    """Validate Row 0 tab buttons, active/inactive styling, and Row 1 actions."""

    @pytest.mark.parametrize("mod", TAB_MODULES)
    def test_row_0_contains_exactly_five_tab_buttons(self, mod: str) -> None:
        """Each SetupPanelView tab instance must contain all 5 tab buttons in Row 0."""
        view = SetupPanelView(current_module=mod)
        tab_buttons = [
            c
            for c in view.children
            if isinstance(c, discord.ui.Button) and str(_get_cid(c) or "").startswith("setup:tab:")
        ]
        assert len(tab_buttons) == 5, f"Expected 5 tab buttons, found {len(tab_buttons)}"
        tab_ids = [_get_cid(c) for c in tab_buttons]
        expected_ids = [f"setup:tab:{m}" for m in TAB_MODULES]
        assert tab_ids == expected_ids

        for btn in tab_buttons:
            assert _get_row(btn) == 0, f"Button {_get_cid(btn)} must be in Row 0"

    @pytest.mark.parametrize("active_mod", TAB_MODULES)
    def test_active_tab_button_visual_state(self, active_mod: str) -> None:
        """The active tab button must have primary style and disabled=True.

        Inactive buttons must have secondary style and disabled=False.
        """
        view = SetupPanelView(current_module=active_mod)
        for child in view.children:
            cid = _get_cid(child)
            if cid and cid.startswith("setup:tab:"):
                tab_name = cid.split(":")[-1]
                assert isinstance(child, discord.ui.Button)
                if tab_name == active_mod:
                    assert child.style == discord.ButtonStyle.primary, (
                        f"Active tab '{tab_name}' must have ButtonStyle.primary"
                    )
                    assert child.disabled is True, f"Active tab '{tab_name}' must be disabled"
                else:
                    assert child.style == discord.ButtonStyle.secondary, (
                        f"Inactive tab '{tab_name}' must have ButtonStyle.secondary"
                    )
                    assert child.disabled is False, f"Inactive tab '{tab_name}' must not be disabled"

    @pytest.mark.parametrize("mod", TAB_MODULES)
    def test_row_1_contains_refresh_and_close(self, mod: str) -> None:
        """Row 1 must contain setup:refresh and setup:close buttons."""
        view = SetupPanelView(current_module=mod)
        row1_buttons = [c for c in view.children if isinstance(c, discord.ui.Button) and _get_row(c) == 1]
        row1_ids = {_get_cid(c) for c in row1_buttons}
        assert "setup:refresh" in row1_ids
        assert "setup:close" in row1_ids

    @pytest.mark.parametrize("mod", TAB_MODULES)
    def test_view_timeout_is_none_and_custom_ids_static(self, mod: str) -> None:
        """All tab views must have timeout=None and static custom_ids starting with setup:."""
        view = SetupPanelView(current_module=mod)
        assert view.timeout is None
        for child in view.children:
            cid = _get_cid(child)
            assert cid is not None, f"Child {child} missing custom_id"
            assert cid.startswith("setup:"), f"Custom ID {cid} must start with setup:"

    @pytest.mark.parametrize("mod", TAB_MODULES)
    def test_view_row_count_does_not_exceed_discord_limit(self, mod: str) -> None:
        """Discord views permit at most 5 action rows (0 through 4)."""
        view = SetupPanelView(current_module=mod)
        rows_used = {_get_row(c) for c in view.children if _get_row(c) is not None}
        assert max(rows_used) <= 4, f"Module {mod} exceeds 5 Discord rows: {rows_used}"
        assert min(rows_used) >= 0

    @pytest.mark.parametrize("mod", TAB_MODULES)
    def test_view_component_limits_and_select_isolation(self, mod: str) -> None:
        """Discord limits: <= 25 items, <= 5 buttons per row, selects isolated on their own row."""
        view = SetupPanelView(current_module=mod)
        assert len(view.children) <= 25, f"Module {mod} exceeds 25 Discord components: {len(view.children)}"
        rows: dict[int, list[discord.ui.Item]] = {}
        for child in view.children:
            r = _get_row(child)
            assert r is not None, f"Child {_get_cid(child)} missing row"
            rows.setdefault(r, []).append(child)

        for r, items in rows.items():
            selects = [i for i in items if isinstance(i, (discord.ui.Select, discord.ui.ChannelSelect))]
            buttons = [i for i in items if isinstance(i, discord.ui.Button)]
            if selects:
                assert len(items) == 1, (
                    f"Row {r} in module {mod} violates select isolation: has select and other items {items}"
                )
            assert len(buttons) <= 5, f"Row {r} in module {mod} exceeds 5 buttons: {len(buttons)}"


class TestSetupTabContextualRows:
    """Validate contextual component placement for each module tab."""

    def test_tickets_tab_components(self) -> None:
        view = SetupPanelView(current_module="tickets")
        cids = {_get_cid(c) for c in view.children}
        expected_ticket_cids = {
            "setup:tickets:create_category",
            "setup:tickets:delete_category",
            "setup:tickets:list_categories",
            "setup:tickets:configure_fields",
        }
        assert expected_ticket_cids.issubset(cids)
        for cid in expected_ticket_cids:
            item = next(c for c in view.children if _get_cid(c) == cid)
            assert _get_row(item) == 2

    def test_log_tab_components(self) -> None:
        view = SetupPanelView(current_module="log")
        channel_select = next(c for c in view.children if _get_cid(c) == "setup:log:select_channel")
        assert isinstance(channel_select, discord.ui.ChannelSelect)
        assert _get_row(channel_select) == 2

        clear_btn = next(c for c in view.children if _get_cid(c) == "setup:log:clear")
        assert isinstance(clear_btn, discord.ui.Button)
        assert _get_row(clear_btn) == 3

        test_btn = next(c for c in view.children if _get_cid(c) == "setup:log:test")
        assert isinstance(test_btn, discord.ui.Button)
        assert _get_row(test_btn) == 3

    def test_welcome_tab_components(self) -> None:
        view = SetupPanelView(current_module="welcome")
        template_select = next(c for c in view.children if _get_cid(c) == "setup:welcome:select_template")
        assert isinstance(template_select, discord.ui.Select)
        assert _get_row(template_select) == 2

        channel_select = next(c for c in view.children if _get_cid(c) == "setup:welcome:select_channel")
        assert isinstance(channel_select, discord.ui.ChannelSelect)
        assert _get_row(channel_select) == 3

        clear_btn = next(c for c in view.children if _get_cid(c) == "setup:welcome:clear")
        assert _get_row(clear_btn) == 4

        test_btn = next(c for c in view.children if _get_cid(c) == "setup:welcome:test")
        assert _get_row(test_btn) == 4

    def test_goodbye_tab_components(self) -> None:
        view = SetupPanelView(current_module="goodbye")
        template_select = next(c for c in view.children if _get_cid(c) == "setup:goodbye:select_template")
        assert isinstance(template_select, discord.ui.Select)
        assert _get_row(template_select) == 2

        channel_select = next(c for c in view.children if _get_cid(c) == "setup:goodbye:select_channel")
        assert isinstance(channel_select, discord.ui.ChannelSelect)
        assert _get_row(channel_select) == 3

        clear_btn = next(c for c in view.children if _get_cid(c) == "setup:goodbye:clear")
        assert _get_row(clear_btn) == 4

        test_btn = next(c for c in view.children if _get_cid(c) == "setup:goodbye:test")
        assert _get_row(test_btn) == 4

    def test_language_tab_components(self) -> None:
        view = SetupPanelView(current_module="language")
        es_btn = next(c for c in view.children if _get_cid(c) == "setup:language:set_es")
        assert isinstance(es_btn, discord.ui.Button)
        assert _get_row(es_btn) == 2

        en_btn = next(c for c in view.children if _get_cid(c) == "setup:language:set_en")
        assert isinstance(en_btn, discord.ui.Button)
        assert _get_row(en_btn) == 2


class TestSetupTabSwitching:
    """Validate switching tabs via button clicks."""

    @pytest.mark.parametrize("target_tab", TAB_MODULES)
    @pytest.mark.asyncio
    async def test_tab_button_click_switches_view(self, target_tab: str) -> None:
        """Clicking any tab button reconstructs SetupPanelView with target tab and edits message."""
        view = SetupPanelView(current_module="tickets")
        button = next(c for c in view.children if _get_cid(c) == f"setup:tab:{target_tab}")

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 12345
        interaction.guild_id = 12345
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = True
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()

        bot = MagicMock()
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=MagicMock(language="es", log_channel_id=None))
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(
            return_value=MagicMock(guild_id="12345", welcome_channel_id=None, goodbye_channel_id=None)
        )
        bot.db = MagicMock()
        bot.db.get_ticket_categories = AsyncMock(return_value=[])
        interaction.client = bot

        await button.callback(interaction)

        interaction.response.edit_message.assert_awaited_once()
        kwargs = interaction.response.edit_message.call_args.kwargs
        new_view = kwargs.get("view")
        assert isinstance(new_view, SetupPanelView)
        assert new_view.current_module == target_tab

        new_embed = kwargs.get("embed")
        assert isinstance(new_embed, discord.Embed)
        footer_text = getattr(new_embed.footer, "text", "")
        assert f"nbpanel|module={target_tab}" in footer_text

    @pytest.mark.asyncio
    async def test_switch_tab_fallback_to_tickets(self) -> None:
        """_switch_tab with unknown module string defaults to tickets."""
        view = SetupPanelView(current_module="tickets")
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 12345
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()
        bot = MagicMock()
        bot.db = MagicMock()
        bot.db.get_ticket_categories = AsyncMock(return_value=[])
        interaction.client = bot

        await view._switch_tab(interaction, "nonexistent_tab_abc")

        interaction.response.edit_message.assert_awaited_once()
        kwargs = interaction.response.edit_message.call_args.kwargs
        new_view = kwargs.get("view")
        assert isinstance(new_view, SetupPanelView)
        assert new_view.current_module == "tickets"


class TestSetupChannelPersistence:
    """Validate channel selection and unlinking for log, welcome, and goodbye tabs."""

    @pytest.mark.asyncio
    async def test_log_select_channel_and_clear(self) -> None:
        mod = LogSetupModule()
        bot = MagicMock()
        bot.guild_service = MagicMock()
        cfg = MagicMock(log_channel_id=None)
        bot.guild_service.get_config = AsyncMock(return_value=cfg)
        bot.guild_service.save_config = AsyncMock()

        # 1. Select channel
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 111
        inter.client = bot
        inter.data = {"values": ["1234567890"]}
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.edit_original_response = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, "select_channel")

        assert cfg.log_channel_id == "1234567890"
        bot.guild_service.save_config.assert_awaited_once_with(cfg)
        inter.edit_original_response.assert_awaited_once()
        edit_view = inter.edit_original_response.call_args.kwargs["view"]
        edit_embed = inter.edit_original_response.call_args.kwargs["embed"]
        assert isinstance(edit_view, SetupPanelView)
        assert edit_view.current_module == "log"
        assert edit_embed.author is not None and edit_embed.author.name
        assert getattr(edit_embed.footer, "text", "") == "nbpanel|module=log"
        inter.followup.send.assert_awaited_once()

        # 2. Clear channel
        bot.guild_service.save_config.reset_mock()
        inter_clear = MagicMock(spec=discord.Interaction)
        inter_clear.guild = MagicMock(spec=discord.Guild)
        inter_clear.guild.id = 111
        inter_clear.client = bot
        inter_clear.response = MagicMock()
        inter_clear.response.defer = AsyncMock()
        inter_clear.edit_original_response = AsyncMock()
        inter_clear.followup = MagicMock()
        inter_clear.followup.send = AsyncMock()

        await mod.handle(inter_clear, "clear")

        assert cfg.log_channel_id is None
        bot.guild_service.save_config.assert_awaited_once_with(cfg)
        inter_clear.edit_original_response.assert_awaited_once()
        clear_view = inter_clear.edit_original_response.call_args.kwargs["view"]
        clear_embed = inter_clear.edit_original_response.call_args.kwargs["embed"]
        assert isinstance(clear_view, SetupPanelView)
        assert clear_view.current_module == "log"
        assert clear_embed.author is not None and clear_embed.author.name
        assert getattr(clear_embed.footer, "text", "") == "nbpanel|module=log"
        inter_clear.followup.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_select_channel_defers_before_save_config(self) -> None:
        """P1.2: Acknowledge/defer before awaiting save_config, then edit original response."""
        mod = LogSetupModule()
        bot = MagicMock()
        bot.guild_service = MagicMock()
        cfg = MagicMock(log_channel_id=None)
        bot.guild_service.get_config = AsyncMock(return_value=cfg)

        call_order: list[str] = []

        async def _fake_defer() -> None:
            call_order.append("defer")

        async def _fake_save(c: Any) -> None:  # noqa: ARG001
            call_order.append("save_config")

        bot.guild_service.save_config = AsyncMock(side_effect=_fake_save)

        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 111
        inter.client = bot
        inter.data = {"values": ["1234567890"]}
        inter.response = MagicMock()
        inter.response.defer = AsyncMock(side_effect=_fake_defer)
        inter.response.is_done.return_value = False
        inter.response.edit_message = AsyncMock()
        inter.edit_original_response = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, "select_channel")

        assert call_order == ["defer", "save_config"]
        inter.response.defer.assert_awaited_once()
        inter.edit_original_response.assert_awaited_once()
        inter.response.edit_message.assert_not_called()
        inter.followup.send.assert_awaited_once()
        kwargs = inter.followup.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_log_clear_defers_before_save_config(self) -> None:
        """P1.2: Acknowledge/defer before awaiting clear save_config, then edit original response."""
        mod = LogSetupModule()
        bot = MagicMock()
        bot.guild_service = MagicMock()
        cfg = MagicMock(log_channel_id="1234567890")
        bot.guild_service.get_config = AsyncMock(return_value=cfg)

        call_order: list[str] = []

        async def _fake_defer() -> None:
            call_order.append("defer")

        async def _fake_save(c: Any) -> None:  # noqa: ARG001
            call_order.append("save_config")

        bot.guild_service.save_config = AsyncMock(side_effect=_fake_save)

        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 111
        inter.client = bot
        inter.response = MagicMock()
        inter.response.defer = AsyncMock(side_effect=_fake_defer)
        inter.response.is_done.return_value = False
        inter.response.edit_message = AsyncMock()
        inter.edit_original_response = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, "clear")

        assert call_order == ["defer", "save_config"]
        inter.response.defer.assert_awaited_once()
        inter.edit_original_response.assert_awaited_once()
        inter.response.edit_message.assert_not_called()
        inter.followup.send.assert_awaited_once()
        kwargs = inter.followup.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_log_save_config_error_avoids_second_response_attempt(self) -> None:
        """P1.2: Error after deferral sends ephemeral followup, avoiding second response."""
        mod = LogSetupModule()
        bot = MagicMock()
        bot.guild_service = MagicMock()
        cfg = MagicMock(log_channel_id=None)
        bot.guild_service.get_config = AsyncMock(return_value=cfg)
        bot.guild_service.save_config = AsyncMock(side_effect=RuntimeError("Database failure"))

        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 111
        inter.client = bot
        inter.data = {"values": ["1234567890"]}
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.response.is_done.return_value = False
        inter.response.send_message = AsyncMock()
        inter.edit_original_response = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, "select_channel")

        inter.response.defer.assert_awaited_once()
        inter.response.send_message.assert_not_called()
        inter.edit_original_response.assert_not_called()
        inter.followup.send.assert_awaited_once()
        kwargs = inter.followup.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_log_late_io_completion(self) -> None:
        """P1.2: Late I/O completion still results in single persistence and edit paths."""
        mod = LogSetupModule()
        bot = MagicMock()
        bot.guild_service = MagicMock()
        cfg = MagicMock(log_channel_id=None)
        bot.guild_service.get_config = AsyncMock(return_value=cfg)

        async def _delayed_save(c: Any) -> None:  # noqa: ARG001
            await asyncio.sleep(0.01)

        bot.guild_service.save_config = AsyncMock(side_effect=_delayed_save)

        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 111
        inter.client = bot
        inter.data = {"values": ["1234567890"]}
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.response.is_done.return_value = False
        inter.edit_original_response = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, "select_channel")

        assert bot.guild_service.save_config.await_count == 1
        assert inter.response.defer.await_count == 1
        assert inter.edit_original_response.await_count == 1
        assert inter.followup.send.await_count == 1

    @pytest.mark.asyncio
    async def test_log_select_channel_failed_defer_aborts_persistence_and_response(self) -> None:
        """P1.2: Failed acknowledgement must abort config mutation and post-response actions."""
        mod = LogSetupModule()
        bot = MagicMock()
        bot.guild_service = MagicMock()
        cfg = MagicMock(log_channel_id=None)
        bot.guild_service.get_config = AsyncMock(return_value=cfg)
        bot.guild_service.save_config = AsyncMock()

        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 111
        inter.client = bot
        inter.data = {"values": ["1234567890"]}
        inter.response = MagicMock()
        inter.response.defer = AsyncMock(side_effect=RuntimeError("Gateway timeout during defer"))
        inter.response.is_done.return_value = False
        inter.response.send_message = AsyncMock()
        inter.edit_original_response = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, "select_channel")

        inter.response.defer.assert_awaited_once()
        bot.guild_service.save_config.assert_not_called()
        assert cfg.log_channel_id is None
        inter.edit_original_response.assert_not_called()
        inter.followup.send.assert_not_called()
        inter.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_clear_failed_defer_aborts_persistence_and_response(self) -> None:
        """P1.2: Failed acknowledgement on clear must abort config mutation and post-response actions."""
        mod = LogSetupModule()
        bot = MagicMock()
        bot.guild_service = MagicMock()
        cfg = MagicMock(log_channel_id="1234567890")
        bot.guild_service.get_config = AsyncMock(return_value=cfg)
        bot.guild_service.save_config = AsyncMock()

        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 111
        inter.client = bot
        inter.response = MagicMock()
        inter.response.defer = AsyncMock(side_effect=RuntimeError("Gateway timeout during clear defer"))
        inter.response.is_done.return_value = False
        inter.response.send_message = AsyncMock()
        inter.edit_original_response = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, "clear")

        inter.response.defer.assert_awaited_once()
        bot.guild_service.save_config.assert_not_called()
        assert cfg.log_channel_id == "1234567890"
        inter.edit_original_response.assert_not_called()
        inter.followup.send.assert_not_called()
        inter.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_select_channel_already_acknowledged_does_not_double_defer(self) -> None:
        """P1.2: Previously acknowledged interaction skips defer and persists without double-ack."""
        mod = LogSetupModule()
        bot = MagicMock()
        bot.guild_service = MagicMock()
        cfg = MagicMock(log_channel_id=None)
        bot.guild_service.get_config = AsyncMock(return_value=cfg)
        bot.guild_service.save_config = AsyncMock()

        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 111
        inter.client = bot
        inter.data = {"values": ["1234567890"]}
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.response.is_done.return_value = True
        inter.edit_original_response = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, "select_channel")

        inter.response.defer.assert_not_called()
        bot.guild_service.save_config.assert_awaited_once_with(cfg)
        assert cfg.log_channel_id == "1234567890"
        inter.edit_original_response.assert_awaited_once()
        inter.followup.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_clear_already_acknowledged_does_not_double_defer(self) -> None:
        """P1.2: Previously acknowledged interaction on clear skips defer and persists without double-ack."""
        mod = LogSetupModule()
        bot = MagicMock()
        bot.guild_service = MagicMock()
        cfg = MagicMock(log_channel_id="1234567890")
        bot.guild_service.get_config = AsyncMock(return_value=cfg)
        bot.guild_service.save_config = AsyncMock()

        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 111
        inter.client = bot
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.response.is_done.return_value = True
        inter.edit_original_response = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, "clear")

        inter.response.defer.assert_not_called()
        bot.guild_service.save_config.assert_awaited_once_with(cfg)
        assert cfg.log_channel_id is None
        inter.edit_original_response.assert_awaited_once()
        inter.followup.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_welcome_select_channel_and_clear(self) -> None:
        mod = WelcomeSetupModule()
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        cfg = MagicMock(welcome_channel_id=None, welcome_template_id="default")
        bot.greeting_service.get_config = AsyncMock(return_value=cfg)
        bot.greeting_service.save_config = AsyncMock()

        # 1. Select channel
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 222
        inter.client = bot
        inter.data = {"values": ["2000000001"]}
        inter.response = MagicMock()
        inter.response.edit_message = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, "select_channel")

        assert cfg.welcome_channel_id == "2000000001"
        bot.greeting_service.save_config.assert_awaited_once_with(cfg)
        inter.response.edit_message.assert_awaited_once()
        edit_view = inter.response.edit_message.call_args.kwargs["view"]
        edit_embed = inter.response.edit_message.call_args.kwargs["embed"]
        assert isinstance(edit_view, SetupPanelView)
        assert edit_view.current_module == "welcome"
        assert edit_embed.author is not None and edit_embed.author.name
        assert getattr(edit_embed.footer, "text", "") == "nbpanel|module=welcome"
        inter.followup.send.assert_awaited_once()

        # 2. Clear channel
        bot.greeting_service.save_config.reset_mock()
        inter_clear = MagicMock(spec=discord.Interaction)
        inter_clear.guild = MagicMock(spec=discord.Guild)
        inter_clear.guild.id = 222
        inter_clear.client = bot
        inter_clear.response = MagicMock()
        inter_clear.response.edit_message = AsyncMock()
        inter_clear.followup = MagicMock()
        inter_clear.followup.send = AsyncMock()

        await mod.handle(inter_clear, "clear")

        assert cfg.welcome_channel_id is None
        bot.greeting_service.save_config.assert_awaited_once_with(cfg)
        inter_clear.response.edit_message.assert_awaited_once()
        clear_view = inter_clear.response.edit_message.call_args.kwargs["view"]
        clear_embed = inter_clear.response.edit_message.call_args.kwargs["embed"]
        assert isinstance(clear_view, SetupPanelView)
        assert clear_view.current_module == "welcome"
        assert clear_embed.author is not None and clear_embed.author.name
        assert getattr(clear_embed.footer, "text", "") == "nbpanel|module=welcome"
        inter_clear.followup.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_goodbye_select_channel_and_clear(self) -> None:
        mod = GoodbyeSetupModule()
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        cfg = MagicMock(goodbye_channel_id=None, goodbye_template_id="default")
        bot.greeting_service.get_config = AsyncMock(return_value=cfg)
        bot.greeting_service.save_config = AsyncMock()

        # 1. Select channel
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 333
        inter.client = bot
        inter.data = {"values": ["3000000001"]}
        inter.response = MagicMock()
        inter.response.edit_message = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, "select_channel")

        assert cfg.goodbye_channel_id == "3000000001"
        bot.greeting_service.save_config.assert_awaited_once_with(cfg)
        inter.response.edit_message.assert_awaited_once()
        edit_view = inter.response.edit_message.call_args.kwargs["view"]
        edit_embed = inter.response.edit_message.call_args.kwargs["embed"]
        assert isinstance(edit_view, SetupPanelView)
        assert edit_view.current_module == "goodbye"
        assert edit_embed.author is not None and edit_embed.author.name
        assert getattr(edit_embed.footer, "text", "") == "nbpanel|module=goodbye"
        inter.followup.send.assert_awaited_once()

        # 2. Clear channel
        bot.greeting_service.save_config.reset_mock()
        inter_clear = MagicMock(spec=discord.Interaction)
        inter_clear.guild = MagicMock(spec=discord.Guild)
        inter_clear.guild.id = 333
        inter_clear.client = bot
        inter_clear.response = MagicMock()
        inter_clear.response.edit_message = AsyncMock()
        inter_clear.followup = MagicMock()
        inter_clear.followup.send = AsyncMock()

        await mod.handle(inter_clear, "clear")

        assert cfg.goodbye_channel_id is None
        bot.greeting_service.save_config.assert_awaited_once_with(cfg)
        inter_clear.response.edit_message.assert_awaited_once()
        clear_view = inter_clear.response.edit_message.call_args.kwargs["view"]
        clear_embed = inter_clear.response.edit_message.call_args.kwargs["embed"]
        assert isinstance(clear_view, SetupPanelView)
        assert clear_view.current_module == "goodbye"
        assert clear_embed.author is not None and clear_embed.author.name
        assert getattr(clear_embed.footer, "text", "") == "nbpanel|module=goodbye"
        inter_clear.followup.send.assert_awaited_once()


class TestSetupLanguagePersistence:
    """Validate language selection (es / en) updates service and rebuilds view."""

    @pytest.mark.parametrize(("action", "lang"), [("set_es", "es"), ("set_en", "en")])
    @pytest.mark.asyncio
    async def test_language_switch_persists_and_edits(self, action: str, lang: str) -> None:
        mod = LanguageSetupModule()
        bot = MagicMock()
        bot.guild_service = MagicMock()
        cfg = MagicMock(language="es" if lang == "en" else "en")
        bot.guild_service.get_config = AsyncMock(return_value=cfg)
        bot.guild_service.save_config = AsyncMock()

        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 444
        inter.client = bot
        inter.response = MagicMock()
        inter.response.edit_message = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        await mod.handle(inter, action)

        assert cfg.language == lang
        bot.guild_service.save_config.assert_awaited_once_with(cfg)
        inter.response.edit_message.assert_awaited_once()
        edit_view = inter.response.edit_message.call_args.kwargs["view"]
        edit_embed = inter.response.edit_message.call_args.kwargs["embed"]
        assert isinstance(edit_view, SetupPanelView)
        assert edit_view.current_module == "language"
        assert edit_embed.author is not None and edit_embed.author.name
        assert getattr(edit_embed.footer, "text", "") == "nbpanel|module=language"


class TestSetupTabBarPermissions:
    """Validate interaction_check permission matrix for tab buttons and contextual items."""

    @pytest.mark.asyncio
    async def test_admin_bypasses_all_checks(self) -> None:
        view = SetupPanelView(current_module="tickets")
        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(spec=discord.Member)
        inter.user.guild_permissions.administrator = True
        inter.data = {"custom_id": "setup:tab:welcome"}

        assert await view.interaction_check(inter) is True

    @pytest.mark.parametrize(
        ("custom_id", "required_perm"),
        [
            ("setup:tab:tickets", "tickets.manage"),
            ("setup:tab:log", "tickets.manage"),
            ("setup:tab:language", "tickets.manage"),
            ("setup:tab:welcome", "greeting.manage"),
            ("setup:tab:goodbye", "greeting.manage"),
        ],
    )
    @pytest.mark.asyncio
    async def test_tab_button_requires_corresponding_permission(self, custom_id: str, required_perm: str) -> None:
        view = SetupPanelView(current_module="tickets")
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 1234
        inter.user = MagicMock(spec=discord.Member)
        inter.user.guild_permissions.administrator = False
        inter.data = {"custom_id": custom_id}
        inter.response = MagicMock()
        inter.response.send_message = AsyncMock()

        # Denied when perm check returns False
        with patch("bot.views.setup_panel.can_member", new=AsyncMock(return_value=False)) as mock_can:
            assert await view.interaction_check(inter) is False
            mock_can.assert_awaited_with(required_perm, inter.user, "1234")
            inter.response.send_message.assert_awaited_once()

        # Granted when perm check returns True
        with patch("bot.views.setup_panel.can_member", new=AsyncMock(return_value=True)) as mock_can:
            assert await view.interaction_check(inter) is True
            mock_can.assert_awaited_with(required_perm, inter.user, "1234")

    @pytest.mark.parametrize(
        ("custom_id", "required_perm"),
        [
            ("setup:tickets:create_category", "tickets.manage"),
            ("setup:tickets:delete_category", "tickets.manage"),
            ("setup:tickets:list_categories", "tickets.manage"),
            ("setup:tickets:configure_fields", "tickets.manage"),
            ("setup:log:select_channel", "tickets.manage"),
            ("setup:log:clear", "tickets.manage"),
            ("setup:language:set_es", "tickets.manage"),
            ("setup:language:set_en", "tickets.manage"),
            ("setup:welcome:select_channel", "greeting.manage"),
            ("setup:welcome:clear", "greeting.manage"),
            ("setup:goodbye:select_channel", "greeting.manage"),
            ("setup:goodbye:clear", "greeting.manage"),
        ],
    )
    @pytest.mark.asyncio
    async def test_contextual_action_requires_corresponding_permission(
        self, custom_id: str, required_perm: str
    ) -> None:
        view = SetupPanelView(current_module="tickets")
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 5678
        inter.user = MagicMock(spec=discord.Member)
        inter.user.guild_permissions.administrator = False
        inter.data = {"custom_id": custom_id}
        inter.response = MagicMock()
        inter.response.send_message = AsyncMock()

        # Denied when perm check returns False
        with patch("bot.views.setup_panel.can_member", new=AsyncMock(return_value=False)) as mock_can:
            assert await view.interaction_check(inter) is False
            mock_can.assert_awaited_with(required_perm, inter.user, "5678")
            inter.response.send_message.assert_awaited_once()

        # Granted when perm check returns True
        with patch("bot.views.setup_panel.can_member", new=AsyncMock(return_value=True)) as mock_can:
            assert await view.interaction_check(inter) is True
            mock_can.assert_awaited_with(required_perm, inter.user, "5678")

    @pytest.mark.parametrize("custom_id", ["setup:refresh", "setup:close"])
    @pytest.mark.asyncio
    async def test_generic_action_allows_any_module_permission(self, custom_id: str) -> None:
        view = SetupPanelView(current_module="tickets")
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 5678
        inter.user = MagicMock(spec=discord.Member)
        inter.user.guild_permissions.administrator = False
        inter.data = {"custom_id": custom_id}
        inter.response = MagicMock()
        inter.response.send_message = AsyncMock()

        # Denied when neither permission is held
        with patch("bot.views.setup_panel.can_member", new=AsyncMock(return_value=False)):
            assert await view.interaction_check(inter) is False
            inter.response.send_message.assert_awaited_once()

        # Granted if either tickets.manage or greeting.manage is held
        async def _mock_can_member(perm: str, _user: Any, _guild_id: str) -> bool:
            return perm == "greeting.manage"

        with patch("bot.views.setup_panel.can_member", new=AsyncMock(side_effect=_mock_can_member)):
            assert await view.interaction_check(inter) is True


class TestSetupTabBarRefreshPreservation:
    """Validate clicking refresh on a panel after module interaction preserves the active tab."""

    @pytest.mark.parametrize("active_mod", TAB_MODULES)
    @pytest.mark.asyncio
    async def test_refresh_preserves_active_tab_from_footer(self, active_mod: str) -> None:
        bot = MagicMock()
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=MagicMock(log_channel_id="999", language="es"))
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(
            return_value=MagicMock(
                welcome_channel_id="111",
                goodbye_channel_id="222",
                welcome_enabled=True,
                goodbye_enabled=True,
            )
        )
        bot.db = MagicMock()
        bot.db.get_ticket_categories = AsyncMock(return_value=[])

        embed = await _build_embed("777", active_mod, bot=bot)
        assert embed.footer is not None
        assert embed.footer.text == f"nbpanel|module={active_mod}"

        msg = MagicMock()
        msg.embeds = [embed]

        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 777
        inter.client = bot
        inter.message = msg
        inter.response = MagicMock()
        inter.response.edit_message = AsyncMock()

        # View handling the interaction might be a persistent view default (e.g. tickets)
        view = SetupPanelView(current_module="tickets", guild_id="777")
        await view.refresh_button.callback(inter)

        inter.response.edit_message.assert_awaited_once()
        rebuilt_view = inter.response.edit_message.call_args.kwargs["view"]
        assert isinstance(rebuilt_view, SetupPanelView)
        assert rebuilt_view.current_module == active_mod, (
            f"Expected refreshed view to stay on '{active_mod}', but got '{rebuilt_view.current_module}'"
        )


class TestSetupTabBarLocalization:
    """Validate tab button labels in Spanish and English."""

    def test_tab_bar_labels_es(self) -> None:
        set_guild_language("888", "es")
        view = SetupPanelView(current_module="tickets", guild_id="888")

        expected_labels = {
            "setup:tab:tickets": "Tickets",
            "setup:tab:welcome": "Entrada",
            "setup:tab:goodbye": "Salida",
            "setup:tab:log": "Logs",
            "setup:tab:language": "Idioma",
        }
        for child in view.children:
            cid = _get_cid(child)
            if cid in expected_labels:
                assert isinstance(child, discord.ui.Button)
                assert child.label == expected_labels[cid], (
                    f"Label for {cid} in ES was {child.label!r}, expected {expected_labels[cid]!r}"
                )

    def test_tab_bar_labels_en(self) -> None:
        set_guild_language("999", "en")
        view = SetupPanelView(current_module="tickets", guild_id="999")

        expected_labels = {
            "setup:tab:tickets": "Tickets",
            "setup:tab:welcome": "Welcome",
            "setup:tab:goodbye": "Goodbye",
            "setup:tab:log": "Logs",
            "setup:tab:language": "Language",
        }
        for child in view.children:
            cid = _get_cid(child)
            if cid in expected_labels:
                assert isinstance(child, discord.ui.Button)
                assert child.label == expected_labels[cid], (
                    f"Label for {cid} in EN was {child.label!r}, expected {expected_labels[cid]!r}"
                )

    def test_row_1_action_labels_localized(self) -> None:
        set_guild_language("888", "es")
        view_es = SetupPanelView(current_module="tickets", guild_id="888")
        refresh_es = next(c for c in view_es.children if _get_cid(c) == "setup:refresh")
        close_es = next(c for c in view_es.children if _get_cid(c) == "setup:close")
        assert isinstance(refresh_es, discord.ui.Button)
        assert isinstance(close_es, discord.ui.Button)
        assert refresh_es.label == "Actualizar"
        assert close_es.label == "Cerrar"

        set_guild_language("999", "en")
        view_en = SetupPanelView(current_module="tickets", guild_id="999")
        refresh_en = next(c for c in view_en.children if _get_cid(c) == "setup:refresh")
        close_en = next(c for c in view_en.children if _get_cid(c) == "setup:close")
        assert isinstance(refresh_en, discord.ui.Button)
        assert isinstance(close_en, discord.ui.Button)
        assert refresh_en.label == "Refresh"
        assert close_en.label == "Close"

    @pytest.mark.parametrize(
        ("lang", "expected_breadcrumbs"),
        [
            (
                "es",
                {
                    "tickets": "Tickets",
                    "welcome": "Bienvenida",
                    "goodbye": "Despedida",
                    "log": "Registro",
                    "language": "Idioma",
                },
            ),
            (
                "en",
                {
                    "tickets": "Tickets",
                    "welcome": "Welcome",
                    "goodbye": "Goodbye",
                    "log": "Log",
                    "language": "Language",
                },
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_embed_author_breadcrumb_localized(self, lang: str, expected_breadcrumbs: dict[str, str]) -> None:
        gid = f"locale_{lang}"
        set_guild_language(gid, lang)
        bot = MagicMock()
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=MagicMock(language=lang, log_channel_id=None))
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(
            return_value=MagicMock(guild_id=gid, welcome_channel_id=None, goodbye_channel_id=None)
        )
        bot.db = MagicMock()
        bot.db.get_ticket_categories = AsyncMock(return_value=[])

        for mod, expected_author in expected_breadcrumbs.items():
            embed = await _build_embed(gid, mod, bot=bot)
            assert embed.author is not None
            assert embed.author.name == expected_author, (
                f"Expected author for {mod} in {lang} to be {expected_author!r}, got {embed.author.name!r}"
            )
            assert getattr(embed.footer, "text", "") == f"nbpanel|module={mod}"


class TestSetupTabBarTemplatePickerPreservesFrame:
    """Validate handle_template_select_flow retains author breadcrumb and footer token."""

    @pytest.mark.parametrize("kind", ["welcome", "goodbye"])
    @pytest.mark.asyncio
    async def test_template_select_preserves_embed_frame(self, kind: Literal["welcome", "goodbye"]) -> None:
        module = WelcomeSetupModule() if kind == "welcome" else GoodbyeSetupModule()
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        cfg = MagicMock(welcome_template_id=None, goodbye_template_id=None)
        bot.greeting_service.get_config = AsyncMock(return_value=cfg)
        bot.greeting_service.save_config = AsyncMock()

        persist_mock = AsyncMock()

        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 555
        inter.client = bot
        inter.data = {"values": ["gaming_neon"]}
        inter.user = MagicMock(spec=discord.Member)
        inter.user.guild_permissions.administrator = True
        inter.response = MagicMock()
        inter.response.edit_message = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        with patch("bot.views.setup_modules._template_picker.can_member", new=AsyncMock(return_value=True)):
            await handle_template_select_flow(module, inter, kind, persist=persist_mock)

        persist_mock.assert_awaited_once_with("555", "gaming_neon", bot)
        inter.response.edit_message.assert_awaited_once()
        edit_embed = inter.response.edit_message.call_args.kwargs["embed"]
        edit_view = inter.response.edit_message.call_args.kwargs["view"]
        assert isinstance(edit_view, SetupPanelView)
        assert edit_view.current_module == kind
        assert edit_embed.author is not None and edit_embed.author.name
        assert getattr(edit_embed.footer, "text", "") == f"nbpanel|module={kind}"


class TestSetupTabBarPersistentRouting:
    """Validate restart persistence and footer token parsing across all tabs."""

    @pytest.mark.asyncio
    async def test_setup_hook_registers_all_five_tab_views(self) -> None:
        registered: list[discord.ui.View] = []
        bot = NebulosaBot(
            config=BotConfig(
                discord_token="t",
                supabase_url="https://x.supabase.co",
                supabase_key="test-key",
            ),
            intents=discord.Intents.default(),
        )
        with (
            patch("bot.bot.Database") as db_cls,
            patch("bot.bot.RealtimeCacheSubscriber") as sub_cls,
            patch.object(bot, "load_extension", new=AsyncMock()),
            patch.object(type(bot.tree), "sync", AsyncMock()),
            patch("bot.bot.load_locales"),
            patch("bot.bot.validate_slash_localizations"),
            patch.object(type(bot.tree), "set_translator", new=AsyncMock()),
            patch.object(type(bot), "add_view", side_effect=lambda view, *, message_id=None: registered.append(view)),
        ):
            db_cls.return_value.connect = AsyncMock()
            sub_cls.return_value.start = AsyncMock()
            await bot.setup_hook()

        panel_views = [v for v in registered if isinstance(v, SetupPanelView)]
        assert len(panel_views) == 5, f"Expected 5 SetupPanelView instances, got {len(panel_views)}"
        registered_modules = [v.current_module for v in panel_views]
        assert registered_modules == list(TAB_MODULES)

        for view in panel_views:
            assert view.timeout is None
            for child in view.children:
                cid = _get_cid(child)
                assert cid is not None
                assert cid.startswith("setup:")

    @pytest.mark.parametrize(
        ("footer_text", "expected_mod"),
        [
            (None, "tickets"),
            ("", "tickets"),
            ("random footer text", "tickets"),
            ("nbpanel|module=tickets", "tickets"),
            ("nbpanel|module=welcome", "welcome"),
            ("nbpanel|module=goodbye", "goodbye"),
            ("nbpanel|module=log", "log"),
            ("nbpanel|module=language", "language"),
            ("nbpanel|module=unknown_foo", "unknown_foo"),
        ],
    )
    def test_parse_module_from_footer_matrix(self, footer_text: str | None, expected_mod: str) -> None:
        if footer_text is None:
            embed = discord.Embed(title="No footer")
        else:
            embed = discord.Embed(title="With footer")
            embed.set_footer(text=footer_text)
        assert _parse_module_from_footer(embed) == expected_mod

    def test_parse_module_from_footer_none_embed(self) -> None:
        assert _parse_module_from_footer(None) == "tickets"
