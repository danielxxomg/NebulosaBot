"""Remediation RED tests — verify-report CRITICAL #1 (SETUP-ROUTE).

The runtime /setup flow must expose and register the per-kind template
pickers:

- ``SetupPanelView`` itself carries both ``setup:{kind}:select_template``
  StringSelects (appended from ``MODULES["welcome"|"goodbye"]``) so the
  interaction the panel actually reaches can route them.
- The persistent view registered by ``bot.setup_hook`` contains both
  custom_ids (restart routing, AGENTS.md persistent-view rule).

Ref: openspec/changes/greeting-templates/verify-report.md CRITICAL #1.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

_WELCOME_SELECT_ID = "setup:welcome:select_template"
_GOODBYE_SELECT_ID = "setup:goodbye:select_template"
_TEMPLATE_IDS = ("default", "gaming_neon", "sunset_wave", "minimal_light")


def _panel_select_ids() -> set[str | None]:
    from bot.views.setup_panel import SetupPanelView  # noqa: PLC0415 -- facade indirection

    view = SetupPanelView()
    return {getattr(c, "custom_id", None) for c in view.children}


class TestPanelCarriesTemplatePickers:
    """SetupPanelView must attach both module template selects at construction."""

    def test_panel_contains_welcome_template_select(self) -> None:
        assert _WELCOME_SELECT_ID in _panel_select_ids(), (
            "SetupPanelView must carry setup:welcome:select_template (runtime /setup reachability)"
        )

    def test_panel_contains_goodbye_template_select(self) -> None:
        assert _GOODBYE_SELECT_ID in _panel_select_ids(), (
            "SetupPanelView must carry setup:goodbye:select_template (runtime /setup reachability)"
        )

    def test_panel_pickers_offer_exactly_four_registry_options(self) -> None:
        """Both panel-attached pickers mirror the four-template registry."""
        from bot.views.setup_panel import SetupPanelView  # noqa: PLC0415 -- facade indirection

        view = SetupPanelView()
        for cid in (_WELCOME_SELECT_ID, _GOODBYE_SELECT_ID):
            select = next(c for c in view.children if getattr(c, "custom_id", None) == cid)
            assert isinstance(select, discord.ui.Select)
            values = tuple(opt.value for opt in select.options)
            assert values == _TEMPLATE_IDS, f"{cid} must offer the four registry options, got {values}"

    def test_panel_pickers_are_persistent(self) -> None:
        """Panel keeps timeout=None with static custom_ids after picker wiring."""
        from bot.views.setup_panel import SetupPanelView  # noqa: PLC0415 -- facade indirection

        view = SetupPanelView()
        assert view.timeout is None
        for child in view.children:
            cid = getattr(child, "custom_id", None)
            if cid is not None:
                assert cid.startswith("setup:"), f"custom_id must stay in the static setup: namespace, got {cid!r}"


def _panel_interaction(
    guild_id: str = "123456789",
    bot: MagicMock | None = None,
    custom_id: str = _WELCOME_SELECT_ID,
    values: list[str] | None = None,
) -> MagicMock:
    """Return a MagicMock Interaction wired for panel picker callbacks."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = int(guild_id)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.guild_permissions.administrator = True
    interaction.response = MagicMock()
    interaction.response.edit_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.data = {"custom_id": custom_id, "values": values or ["sunset_wave"]}
    interaction.client = bot
    return interaction


class TestPanelPickerRouting:
    """Panel picker callbacks must route through the module handle() (greeting.manage gated)."""

    @pytest.mark.parametrize(
        ("kind", "select_id", "value", "saved_attr", "other_attr", "other_val"),
        [
            pytest.param(
                "welcome",
                _WELCOME_SELECT_ID,
                "sunset_wave",
                "welcome_template_id",
                "goodbye_template_id",
                None,
                id="welcome",
            ),
            pytest.param(
                "goodbye",
                _GOODBYE_SELECT_ID,
                "minimal_light",
                "goodbye_template_id",
                "welcome_template_id",
                "sunset_wave",
                id="goodbye",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_panel_select_routes_to_module_handler(
        self,
        kind: str,
        select_id: str,
        value: str,
        saved_attr: str,
        other_attr: str,
        other_val: str | None,
    ) -> None:
        """Panel-attached {kind} select persists the picked value via the module path (kind-scoped)."""
        from bot.views.setup_panel import SetupPanelView  # noqa: PLC0415 -- facade indirection

        guild_id = "123456789"
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(
            return_value=MagicMock(
                guild_id=guild_id,
                welcome_template_id="sunset_wave" if kind == "goodbye" else None,  # noqa: RUF034
                goodbye_template_id=None if kind == "welcome" else None,  # noqa: RUF034
                theme_id=None,
            )
        )
        bot.greeting_service.save_config = AsyncMock(return_value=None)

        view = SetupPanelView()
        select = next(c for c in view.children if getattr(c, "custom_id", None) == select_id)
        assert isinstance(select, discord.ui.Select)

        interaction = _panel_interaction(guild_id=guild_id, bot=bot, custom_id=select_id, values=[value])

        await select.callback(interaction)

        assert bot.greeting_service.save_config.await_count == 1, (
            f"panel-attached {kind} picker must persist through the module handler"
        )
        saved = bot.greeting_service.save_config.call_args.args[0]
        assert getattr(saved, saved_attr) == value
        if other_val is not None:
            assert getattr(saved, other_attr) == other_val, f"{other_attr} must stay kind-scoped"
        _ = kind

    # --- 3.1 RED: strengthened assertion — children/type/custom_id inspection ---
    # Modeled on :279-286 children inspection; watches FAIL against weak :192-197 state.

    @pytest.mark.asyncio
    async def test_panel_select_refresh_retains_view_with_select_child(self) -> None:
        """RED (3.1): edit_message view must retain its Select child with correct custom_id.

        Strengthened sibling of test_panel_select_refresh_keeps_panel_controls: the weak
        ``view is not None`` check would pass for ``discord.ui.View()`` (empty) or any
        truthy view; this test requires the rebuilt view to carry a ``discord.ui.Select``
        whose ``custom_id`` is the triggered kind's picker id.
        """
        from bot.views.setup_panel import SetupPanelView  # noqa: PLC0415 -- facade indirection

        guild_id = "123456789"
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(
            return_value=MagicMock(
                guild_id=guild_id,
                welcome_template_id=None,
                goodbye_template_id=None,
                theme_id=None,
            )
        )
        bot.greeting_service.save_config = AsyncMock(return_value=None)

        view = SetupPanelView()
        select = next(c for c in view.children if getattr(c, "custom_id", None) == _WELCOME_SELECT_ID)
        assert isinstance(select, discord.ui.Select)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = int(guild_id)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = True
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.data = {"custom_id": _WELCOME_SELECT_ID, "values": ["sunset_wave"]}
        interaction.client = bot

        await select.callback(interaction)

        assert interaction.response.edit_message.await_count == 1
        kwargs = interaction.response.edit_message.call_args.kwargs
        edited_view = kwargs.get("view")
        assert isinstance(edited_view, discord.ui.View), (
            "panel edit must retain a discord.ui.View — discord.py serializes view=None as components: []"
        )
        assert edited_view.children, (
            "panel edit View must retain controls — empty View strips the message like view=None"
        )
        child_ids = {getattr(c, "custom_id", None) for c in edited_view.children}
        assert _WELCOME_SELECT_ID in child_ids, f"refresh View must rebuild the welcome picker, got {child_ids}"
        rebuilt = next(c for c in edited_view.children if getattr(c, "custom_id", None) == _WELCOME_SELECT_ID)
        assert isinstance(rebuilt, discord.ui.Select)

    @pytest.mark.asyncio
    async def test_panel_select_refresh_keeps_panel_controls(self) -> None:
        """After a picker selection the panel edit must not strip components (no view=None)."""
        from bot.views.setup_panel import SetupPanelView  # noqa: PLC0415 -- facade indirection

        guild_id = "123456789"
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(
            return_value=MagicMock(
                guild_id=guild_id,
                welcome_template_id=None,
                goodbye_template_id=None,
                theme_id=None,
            )
        )
        bot.greeting_service.save_config = AsyncMock(return_value=None)

        view = SetupPanelView()
        select = next(c for c in view.children if getattr(c, "custom_id", None) == _WELCOME_SELECT_ID)
        assert isinstance(select, discord.ui.Select)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = int(guild_id)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = True
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.data = {"custom_id": _WELCOME_SELECT_ID, "values": ["sunset_wave"]}
        interaction.client = bot

        await select.callback(interaction)

        assert interaction.response.edit_message.await_count == 1
        kwargs = interaction.response.edit_message.call_args.kwargs
        edited_view = kwargs.get("view")
        assert isinstance(edited_view, discord.ui.View), (
            "panel edit must retain a discord.ui.View — discord.py serializes view=None as components: []"
        )
        assert edited_view.children, (
            "panel edit View must retain controls — empty View strips the message like view=None"
        )
        child_ids = {getattr(c, "custom_id", None) for c in edited_view.children}
        assert _WELCOME_SELECT_ID in child_ids, f"refresh View must rebuild the welcome picker, got {child_ids}"
        rebuilt = next(c for c in edited_view.children if getattr(c, "custom_id", None) == _WELCOME_SELECT_ID)
        assert isinstance(rebuilt, discord.ui.Select)

    @pytest.mark.asyncio
    async def test_panel_picker_denies_without_greeting_manage(self) -> None:
        """Non-granted user through the panel picker → ephemeral denial, no mutation."""
        from bot.views.setup_panel import SetupPanelView  # noqa: PLC0415 -- facade indirection

        guild_id = "123456789"
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(return_value=MagicMock(guild_id=guild_id))
        bot.greeting_service.save_config = AsyncMock(return_value=None)

        view = SetupPanelView()
        select = next(c for c in view.children if getattr(c, "custom_id", None) == _WELCOME_SELECT_ID)
        assert isinstance(select, discord.ui.Select)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = int(guild_id)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = False
        interaction.user.roles = []
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.data = {"custom_id": _WELCOME_SELECT_ID, "values": ["sunset_wave"]}
        interaction.client = bot

        with patch("bot.views.setup_panel.can_member", new=AsyncMock(return_value=False)):
            assert await view.interaction_check(interaction) is False
        # Module-level gate must also deny (defense in depth, same key).
        with patch("bot.views.setup_modules.welcome.can_member", new=AsyncMock(return_value=False)):
            await select.callback(interaction)

        bot.greeting_service.save_config.assert_not_awaited()
        ephemeral = interaction.response.send_message.await_count + interaction.followup.send.await_count
        assert ephemeral >= 1, "denial must surface ephemerally"


class TestSetupHookRegistersPanelWithPickers:
    """bot.setup_hook registers the persistent SetupPanelView that now carries the pickers."""

    @pytest.mark.asyncio
    async def test_setup_hook_registers_panel_with_both_template_pickers(self) -> None:
        """Executing setup_hook must add_view() a SetupPanelView carrying both custom_ids.

        Runtime proof (not source-text matching): the real ``NebulosaBot.setup_hook``
        runs with DB/cache/extensions mocked (house harness from ``test_bot_probe.py``)
        and every ``add_view`` call is captured. Registration counts only if the
        registered object IS a ``SetupPanelView`` instance whose children include both
        ``setup:{kind}:select_template`` custom_ids — a plain ``View`` or an unrelated
        class fails the assertion.
        """
        from bot.bot import NebulosaBot  # noqa: PLC0415 -- facade indirection
        from bot.config import BotConfig  # noqa: PLC0415 -- facade indirection
        from bot.views.setup_panel import SetupPanelView  # noqa: PLC0415 -- facade indirection

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

        panels = [v for v in registered if isinstance(v, SetupPanelView)]
        assert panels, "setup_hook must execute add_view() with a SetupPanelView instance"
        child_ids = {getattr(c, "custom_id", None) for c in panels[0].children}
        assert _WELCOME_SELECT_ID in child_ids, (
            "registered panel must carry setup:welcome:select_template (restart routing)"
        )
        assert _GOODBYE_SELECT_ID in child_ids, (
            "registered panel must carry setup:goodbye:select_template (restart routing)"
        )
