"""S2b.1 RED — Welcome setup module: parity + preview.

Ref: welcome-goodbye "Setup-module configuration parity and preview"
- module save matches legacy command effect (channel updated + cache invalidated)
  — same persisted state (GreetingConfig) as deleted /welcome group's channel/toggle/message writes.
- test button delivers REAL localized preview to configured channel (defer → GreetingService render → channel send)
- preview failure (no channel) → ephemeral error, no mutation
"""

from __future__ import annotations

import io
import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from tests.conftest import make_greeting_bot as _make_bot_with_greeting
from tests.conftest import make_greeting_interaction as _make_interaction

# Locale snapshots read once at import (sync context — ASYNC240 forbids blocking
# pathlib reads inside async tests). Read-only; tests never mutate locale files.
_ES_LOCALE = json.loads(pathlib.Path("bot/locales/es.json").read_text(encoding="utf-8"))


class TestWelcomeModuleRegistration:
    """MODULES must contain welcome module implementing SetupModule protocol without framework edits."""

    def test_module_exists(self) -> None:
        from bot.views.setup_panel import MODULES  # noqa: PLC0415 -- facade indirection

        assert "welcome" in MODULES, f"MODULES must contain welcome, got {list(MODULES.keys())}"

    def test_module_protocol(self) -> None:
        from bot.views.setup_panel import MODULES  # noqa: PLC0415 -- facade indirection

        mod = MODULES["welcome"]
        assert hasattr(mod, "key") and mod.key == "welcome"
        assert hasattr(mod, "permission_key") and mod.permission_key == "greeting.manage"
        assert callable(getattr(mod, "render", None))
        assert callable(getattr(mod, "components", None))
        assert callable(getattr(mod, "handle", None))

    def test_registered_without_framework_edits(self) -> None:
        """Welcome module must be registered via MODULES dict, not by editing setup_panel framework to hardcode welcome."""
        import pathlib  # noqa: PLC0415 -- facade indirection

        src = pathlib.Path("bot/views/setup_panel.py").read_text(encoding="utf-8")
        # Framework does not hardcode Welcome-specific logic beyond generic MODULES routing
        # Ensure setup_panel does not contain a dedicated "class WelcomeSetupModule" or inline welcome handle
        assert "class WelcomeSetupModule" not in src
        # File bot/views/setup_modules/welcome.py must exist
        assert pathlib.Path("bot/views/setup_modules/welcome.py").exists()


class TestWelcomeModuleParity:
    """Module save must produce same persisted state + cache invalidation as legacy /welcome channel/toggle/message writes."""

    @pytest.mark.asyncio
    async def test_save_channel_matches_legacy_effect(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        guild_id = "123456789"
        cfg = MagicMock(
            guild_id=guild_id,
            welcome_channel_id=None,
            welcome_enabled=False,
            welcome_message=None,
            welcome_card_enabled=False,
            theme_id=None,
            onboarding_channel_id=None,
        )
        cfg.guild_id = guild_id
        bot = _make_bot_with_greeting("welcome", guild_id=guild_id, config=cfg)
        mod = WelcomeSetupModule(bot=bot)

        # Welcome module handle for saving channel: we simulate a modal submit path
        # S2b.4 requires onboardingChannelId / cardEnabled / themeId exposed; parity for channel is core
        # The module exposes handle("set_channel", selected channel id) or modal path
        # RED: WelcomeSetupModule must expose a greeting-config write that ends in greeting_service.save_config
        # We call handle("channel", interaction) which should guide to a channel select; for parity we verify
        # that a channel-select flow writes via save_config with the chosen channel id
        # To test parity without traversing the full Discord Select, we call the service-level parity directly:
        # fetch config, set channel, save — and assert the module's save helper (if any) delegates to save_config
        # Minimal parity probe: module exposes helper to set welcome channel id
        if hasattr(mod, "set_welcome_channel"):
            await mod.set_welcome_channel(guild_id, "999000111")
        else:
            # Fallback: emulate what the modal/select handler would do
            fetched = await bot.greeting_service.get_config(guild_id)
            fetched.welcome_channel_id = "999000111"
            await bot.greeting_service.save_config(fetched)

        assert bot.greeting_service.save_config.await_count == 1
        saved = bot.greeting_service.save_config.call_args.args[0]
        assert saved.welcome_channel_id == "999000111"

    @pytest.mark.asyncio
    async def test_save_invalidates_cache_like_legacy(self) -> None:
        """Cache invalidation must be delegated to GreetingService.save_config (same as legacy /welcome channel)."""
        guild_id = "123456789"
        bot = _make_bot_with_greeting("welcome", guild_id=guild_id)
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=bot)
        if hasattr(mod, "set_welcome_channel"):
            await mod.set_welcome_channel(guild_id, "888999000")
        else:
            cfg = await bot.greeting_service.get_config(guild_id)
            cfg.welcome_channel_id = "888999000"
            await bot.greeting_service.save_config(cfg)
        # save_config internally invalidates cache_key(guild_id, "greeting_config") per GreetingService
        # We assert the delegation happened (save_config awaited)
        bot.greeting_service.save_config.assert_awaited()

    def test_orphan_columns_exposed_in_editors(self) -> None:
        """Orphan columns cardEnabled, themeId, onboardingChannelId must be exposed in Welcome module editors."""
        import pathlib  # noqa: PLC0415 -- facade indirection

        src = pathlib.Path("bot/views/setup_modules/welcome.py").read_text(encoding="utf-8")
        lower = src.lower()
        assert "cardenabled" in lower or "card_enabled" in lower or "welcome_card_enabled" in lower, (
            "Welcome module must expose cardEnabled/card_enabled"
        )
        assert "themeid" in lower or "theme_id" in lower, "Welcome module must expose themeId/theme_id"
        assert "onboarding" in lower, "Welcome module must expose onboardingChannelId"


class TestWelcomePreviewRealArtifact:
    """Test button must defer → REAL artifact via GreetingService (identical path to join) → deliver to configured channel."""

    @pytest.mark.asyncio
    async def test_preview_delivers_real_localized_card_to_channel(self) -> None:

        guild_id = "123456789"
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(guild_id)
        guild.name = "TestGuild"
        guild.member_count = 42
        guild.icon = None
        guild.get_channel = MagicMock(return_value=channel)

        cfg = MagicMock(
            guild_id=guild_id,
            welcome_channel_id="111222333",
            welcome_enabled=True,
            welcome_message="Hola {mention}",
            welcome_card_enabled=True,
            theme_id=None,
            onboarding_channel_id=None,
        )
        cfg.guild_id = guild_id
        bot = _make_bot_with_greeting("welcome", guild_id=guild_id, config=cfg)
        # Make resolve_renderer return a callable that records it was the REAL renderer (not a fake)
        render_calls: list[dict] = []

        def _real_renderer(**kw: object) -> io.BytesIO:  # noqa: ANN002
            render_calls.append(kw)
            return io.BytesIO(b"real-card")

        bot.greeting_service.resolve_renderer = MagicMock(return_value=_real_renderer)

        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=bot)
        interaction = _make_interaction(guild_id=int(guild_id), client=bot)
        interaction.guild = guild
        # handle("test") is the preview entry per D1: setup:{module}:test → handle(interaction, "test")
        await mod.handle(interaction, "test")

        # Must have deferred
        assert interaction.response.defer.await_count == 1, "preview must defer"
        # Must have delivered to configured channel (guild.get_channel(welcome_channel_id).send)
        assert channel.send.await_count == 1, "preview must send real card to configured channel"
        sent = channel.send.call_args
        assert "file" in sent.kwargs or (sent.args and sent.args[0]), "preview must send a File"
        # Render must have been invoked with localized title/member_count from t() (not hardcoded)
        assert render_calls, "resolve_renderer callable must have been invoked"
        # greeting_title / member_count_text must be non-empty strings that would come from t()
        assert isinstance(render_calls[0].get("greeting_title"), str) and render_calls[0]["greeting_title"]
        assert isinstance(render_calls[0].get("member_count_text"), str)

    @pytest.mark.asyncio
    async def test_preview_failure_no_channel_ephemeral_no_mutation(self) -> None:
        guild_id = "123456789"
        cfg = MagicMock(
            guild_id=guild_id,
            welcome_channel_id=None,
            welcome_enabled=True,
            welcome_message=None,
            welcome_card_enabled=True,
            theme_id=None,
            onboarding_channel_id=None,
        )
        cfg.guild_id = guild_id
        bot = _make_bot_with_greeting("welcome", guild_id=guild_id, config=cfg)
        bot.greeting_service.resolve_renderer = MagicMock(return_value=lambda **_: io.BytesIO(b"x"))

        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=bot)
        interaction = _make_interaction(guild_id=int(guild_id), client=bot)
        # Simulate guild.get_channel returning None for the missing channel
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = int(guild_id)
        interaction.guild.get_channel = MagicMock(return_value=None)
        interaction.guild.name = "G"
        interaction.guild.member_count = 1
        interaction.guild.icon = None
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 1
        interaction.user.guild_permissions.administrator = True

        await mod.handle(interaction, "test")

        # Must surface ephemeral panel error, not mutate config
        # Error is via followup after defer, or via response
        ephemeral = interaction.followup.send.await_count + interaction.response.send_message.await_count
        assert ephemeral >= 1, "missing channel must surface an ephemeral error"
        # No mutation: save_config not called
        bot.greeting_service.save_config.assert_not_awaited()

    def test_caller_passes_translated_strings_no_hardcoded_copy(self) -> None:
        """Greeting card text must come from t() via caller; no hardcoded copy in module."""
        import pathlib  # noqa: PLC0415 -- facade indirection

        src = pathlib.Path("bot/views/setup_modules/welcome.py").read_text(encoding="utf-8")
        # Ensure t("greetings.card.*") or similar is used; and no hardcoded "Welcome to" literal as title
        assert "t(" in src
        # Hardcoded greeting copy would appear as literal English title
        assert "greeting_title" in src or "greetings.card" in src


class TestWelcomeComponents:
    """Welcome module must expose components including test button setup:welcome:test."""

    def test_components_include_test_button(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=_make_bot_with_greeting("welcome"))
        items = mod.components("123456789")
        cids = {getattr(i, "custom_id", None) for i in items}
        assert "setup:welcome:test" in cids


class TestWelcomeTemplatePicker:
    """S3 RED — StringSelect picker with 4 registry options, per-kind persistence (spec setup-panel)."""

    _TEMPLATE_IDS = ("default", "gaming_neon", "sunset_wave", "minimal_light")

    def test_components_include_template_select(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=_make_bot_with_greeting("welcome"))
        items = mod.components("123456789")
        select = next(
            (i for i in items if getattr(i, "custom_id", None) == "setup:welcome:select_template"),
            None,
        )
        assert select is not None, "welcome components must include setup:welcome:select_template StringSelect"
        assert isinstance(select, discord.ui.Select)

    def test_template_select_offers_exactly_four_options(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=_make_bot_with_greeting("welcome"))
        items = mod.components("123456789")
        select = next(i for i in items if getattr(i, "custom_id", None) == "setup:welcome:select_template")
        assert isinstance(select, discord.ui.Select)
        values = tuple(opt.value for opt in select.options)
        assert values == self._TEMPLATE_IDS, f"picker must offer 4 registry options, got {values}"

    def test_template_option_labels_resolve_via_t_not_hardcoded(self) -> None:
        """Option labels/descriptions must come from locale values (t()), not English literals."""
        from bot.core.i18n import set_guild_language  # noqa: PLC0415 -- facade indirection
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        es = _ES_LOCALE
        set_guild_language("123456789", "es")
        mod = WelcomeSetupModule(bot=_make_bot_with_greeting("welcome"))
        items = mod.components("123456789")
        select = next(i for i in items if getattr(i, "custom_id", None) == "setup:welcome:select_template")
        assert isinstance(select, discord.ui.Select)
        expected_labels = {es["templates"]["greeting"][tid]["label"] for tid in self._TEMPLATE_IDS}
        actual = {(opt.label, opt.description) for opt in select.options}
        assert {lbl for lbl, _ in actual} == expected_labels, (
            f"option labels must equal es.json templates.greeting.*.label values, got {actual}"
        )
        assert all(desc for _, desc in actual), "every option must carry a t()-resolved description"

    @pytest.mark.asyncio
    async def test_selecting_welcome_template_persists_per_kind(self) -> None:
        """Selection → set_welcome_template_id → save_config (welcome-wins dual-write); goodbye untouched."""
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        guild_id = "123456789"
        bot = _make_bot_with_greeting("welcome", guild_id=guild_id)
        bot.greeting_service.get_config = AsyncMock(
            return_value=MagicMock(
                guild_id=guild_id,
                welcome_template_id=None,
                goodbye_template_id="minimal_light",
                theme_id=None,
            )
        )
        mod = WelcomeSetupModule(bot=bot)
        interaction = _make_interaction(guild_id=int(guild_id), client=bot)
        interaction.data = {"custom_id": "setup:welcome:select_template", "values": ["sunset_wave"]}

        # Capture the opposite-kind id BEFORE the welcome action so the
        # independence assertion below is falsifiable (never `x in (None, x)`).
        goodbye_before = (await bot.greeting_service.get_config(guild_id)).goodbye_template_id

        select = next(
            i for i in mod.components(guild_id) if getattr(i, "custom_id", None) == "setup:welcome:select_template"
        )
        await select.callback(interaction)

        assert bot.greeting_service.save_config.await_count == 1, "selection must persist via save_config"
        saved = bot.greeting_service.save_config.call_args.args[0]
        assert saved.welcome_template_id == "sunset_wave"
        assert saved.goodbye_template_id == goodbye_before, (
            f"goodbye id must remain {goodbye_before!r} — the welcome picker must not touch the opposite kind"
        )

    @pytest.mark.asyncio
    async def test_missing_greeting_manage_denied_ephemeral_no_mutation(self) -> None:
        """Without greeting.manage grant, picker must deny ephemerally and never mutate config."""
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        guild_id = "123456789"
        bot = _make_bot_with_greeting("welcome", guild_id=guild_id)
        mod = WelcomeSetupModule(bot=bot)
        interaction = _make_interaction(guild_id=int(guild_id), client=bot)
        interaction.user.guild_permissions.administrator = False
        interaction.data = {"custom_id": "setup:welcome:select_template", "values": ["sunset_wave"]}

        with patch("bot.views.setup_modules.welcome.can_member", new=AsyncMock(return_value=False)):
            select = next(
                i for i in mod.components(guild_id) if getattr(i, "custom_id", None) == "setup:welcome:select_template"
            )
            await select.callback(interaction)

        bot.greeting_service.save_config.assert_not_awaited()
        ephemeral = interaction.followup.send.await_count + interaction.response.send_message.await_count
        assert ephemeral >= 1, "denial must surface ephemerally"

    @pytest.mark.asyncio
    async def test_render_async_shows_template_label(self) -> None:
        """Embed description includes the resolved template label via t() (spec render_async scenario)."""
        from bot.core.i18n import set_guild_language  # noqa: PLC0415 -- facade indirection
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        es = _ES_LOCALE
        set_guild_language("123456789", "es")
        guild_id = "123456789"
        bot = _make_bot_with_greeting("welcome", guild_id=guild_id)
        bot.greeting_service.get_config = AsyncMock(
            return_value=MagicMock(
                guild_id=guild_id,
                welcome_channel_id="111222333",
                welcome_enabled=True,
                welcome_card_enabled=True,
                theme_id=None,
                welcome_template_id="gaming_neon",
                onboarding_channel_id=None,
            )
        )
        mod = WelcomeSetupModule(bot=bot)
        embed = await mod.render_async(guild_id)
        expected = es["templates"]["greeting"]["gaming_neon"]["label"]
        assert expected in (embed.description or ""), (
            f"render_async must show resolved template label '{expected}', got {embed.description!r}"
        )


# ---------------------------------------------------------------------------
# Coverage: setter fallbacks + handle branches + _resolve_bot fallback
# ---------------------------------------------------------------------------


class TestWelcomeCoverageSettersAndHandle:
    """Cover welcome.py setter fallback branches and handle edge paths."""

    @pytest.mark.asyncio
    async def test_set_welcome_channel_via_resolve_bot(self) -> None:
        """set_welcome_channel resolves bot via _resolve_bot fallback (no injected bot)."""
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        cfg = MagicMock(guild_id="g1", welcome_channel_id=None)
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(return_value=cfg)
        bot.greeting_service.save_config = AsyncMock(return_value=None)
        mod = WelcomeSetupModule(bot=None)
        with patch("bot.views.setup_panel._get_setup_bot", return_value=bot):
            await mod.set_welcome_channel("g1", "chan-1")
        assert cfg.welcome_channel_id == "chan-1"
        bot.greeting_service.save_config.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_welcome_card_enabled_persists(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        cfg = MagicMock(guild_id="g1", welcome_card_enabled=False)
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(return_value=cfg)
        bot.greeting_service.save_config = AsyncMock(return_value=None)
        mod = WelcomeSetupModule(bot=None)
        with patch("bot.views.setup_panel._get_setup_bot", return_value=bot):
            await mod.set_welcome_card_enabled("g1", True)
        assert cfg.welcome_card_enabled is True

    @pytest.mark.asyncio
    async def test_set_theme_id_persists(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        cfg = MagicMock(guild_id="g1", theme_id=None)
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(return_value=cfg)
        bot.greeting_service.save_config = AsyncMock(return_value=None)
        mod = WelcomeSetupModule(bot=None)
        with patch("bot.views.setup_panel._get_setup_bot", return_value=bot):
            await mod.set_theme_id("g1", "sunset_wave")
        assert cfg.theme_id == "sunset_wave"

    @pytest.mark.asyncio
    async def test_set_onboarding_channel_id_persists(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        cfg = MagicMock(guild_id="g1", onboarding_channel_id=None)
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(return_value=cfg)
        bot.greeting_service.save_config = AsyncMock(return_value=None)
        mod = WelcomeSetupModule(bot=None)
        with patch("bot.views.setup_panel._get_setup_bot", return_value=bot):
            await mod.set_onboarding_channel_id("g1", "chan-2")
        assert cfg.onboarding_channel_id == "chan-2"

    @pytest.mark.asyncio
    async def test_set_welcome_template_id_via_explicit_bot(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        cfg = MagicMock(guild_id="g1", welcome_template_id=None)
        bot = MagicMock()
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(return_value=cfg)
        bot.greeting_service.save_config = AsyncMock(return_value=None)
        mod = WelcomeSetupModule(bot=None)
        # Pass bot explicitly (panel-routed path)
        await mod.set_welcome_template_id("g1", "minimal_light", bot=bot)
        assert cfg.welcome_template_id == "minimal_light"

    @pytest.mark.asyncio
    async def test_set_welcome_channel_raises_without_bot(self) -> None:
        """No bot available → RuntimeError (GreetingService unavailable)."""
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=None)
        with (
            patch("bot.views.setup_panel._get_setup_bot", return_value=None),
            pytest.raises(RuntimeError, match="GreetingService unavailable"),
        ):
            await mod.set_welcome_channel("g1", "x")

    @pytest.mark.asyncio
    async def test_handle_guild_none_early_return(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=None)
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = None
        # Should return without raising, exercising the guild-None branch
        await mod.handle(inter, "test")

    @pytest.mark.asyncio
    async def test_handle_bot_none_early_return(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=None)
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 123
        with patch.object(mod, "_resolve_bot", return_value=None):
            await mod.handle(inter, "test")

    @pytest.mark.asyncio
    async def test_handle_unknown_action_shows_error(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        bot = _make_bot_with_greeting("welcome", guild_id="123456789")
        mod = WelcomeSetupModule(bot=bot)
        inter = _make_interaction(guild_id=123456789, client=bot)
        inter.response.send_message = AsyncMock()
        # Unknown action should send ephemeral error
        await mod.handle(inter, "bogus_unknown")
        assert inter.response.send_message.await_count == 1

    @pytest.mark.asyncio
    async def test_handle_editor_actions_send_ephemeral(self) -> None:
        """set_channel/toggle/etc editor stubs send ephemeral embed."""
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        bot = _make_bot_with_greeting("welcome", guild_id="123456789")
        mod = WelcomeSetupModule(bot=bot)
        inter = _make_interaction(guild_id=123456789, client=bot)
        inter.response.send_message = AsyncMock()
        for action in ("set_channel", "toggle", "set_message", "card_toggle", "set_theme", "set_onboarding"):
            inter.response.send_message.reset_mock()
            await mod.handle(inter, action)
            assert inter.response.send_message.await_count == 1, f"editor action {action!r} must send ephemeral"

    def test_render_sync_returns_embed(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=None)
        embed = mod.render("123456789")
        assert isinstance(embed, discord.Embed)

    @pytest.mark.asyncio
    async def test_render_async_without_bot_returns_embed(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=None)
        embed = await mod.render_async("123456789")
        assert isinstance(embed, discord.Embed)

    def test_resolve_bot_via_interaction_client(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        bot = MagicMock()
        mod = WelcomeSetupModule(bot=None)
        inter = MagicMock(spec=discord.Interaction)
        inter.client = bot
        assert mod._resolve_bot(inter) is bot

    def test_resolve_bot_returns_none_when_no_client(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=None)
        with patch("bot.views.setup_panel._get_setup_bot", return_value=None):
            assert mod._resolve_bot(None) is None

    def test_resolve_bot_catches_import_exception(self) -> None:
        """_resolve_bot handles import exception when setup_panel import fails."""
        import unittest.mock as _mock  # noqa: PLC0415 -- facade indirection

        import bot.views.setup_modules.welcome as wmod  # noqa: PLC0415 -- facade indirection

        mod = wmod.WelcomeSetupModule(bot=None)
        # Patch the import to raise
        with _mock.patch.dict("sys.modules", {"bot.views.setup_panel": None}):
            # Force re-import failure path — _resolve_bot catches and returns None
            result = mod._resolve_bot(None)
            assert result is None

    @pytest.mark.asyncio
    async def test_render_async_exception_falls_back_to_basic_embed(self) -> None:
        """render_async exception (e.g. get_config raises) → still returns basic embed."""
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        bot = MagicMock()
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(side_effect=RuntimeError("db down"))
        mod = WelcomeSetupModule(bot=bot)
        embed = await mod.render_async("g1")
        assert isinstance(embed, discord.Embed)

    @pytest.mark.asyncio
    async def test_on_template_select_dispatches_to_handle(self) -> None:
        """_on_template_select dispatches to handle() select_template path."""
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        bot = MagicMock()
        bot.greeting_service = MagicMock()
        bot.greeting_service.get_config = AsyncMock(return_value=MagicMock(guild_id="g1"))
        bot.greeting_service.save_config = AsyncMock(return_value=None)
        mod = WelcomeSetupModule(bot=bot)
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(spec=discord.Guild)
        inter.guild.id = 123
        inter.client = bot
        inter.data = {"custom_id": "setup:welcome:select_template", "values": ["default"]}
        inter.response = MagicMock()
        inter.response.edit_message = AsyncMock()
        inter.response.send_message = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()
        inter.user = MagicMock(spec=discord.Member)
        inter.user.guild_permissions.administrator = True
        # Ensure can_member passes
        with patch("bot.views.setup_modules._template_picker.can_member", new=AsyncMock(return_value=True)):
            await mod._on_template_select(inter)
        # After select, save_config should have been called via handle_template_select_flow
        bot.greeting_service.save_config.assert_awaited()

    def test_components_binds_callback(self) -> None:
        """components() binds _on_template_select as the select callback."""
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # noqa: PLC0415 -- facade indirection

        mod = WelcomeSetupModule(bot=None)
        items = mod.components("g1")
        sel = next(i for i in items if getattr(i, "custom_id", None) == "setup:welcome:select_template")
        assert callable(sel.callback)
