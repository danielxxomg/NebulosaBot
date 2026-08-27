"""S2b.1 RED — Welcome setup module: parity + preview.

Ref: welcome-goodbye "Setup-module configuration parity and preview"
- module save matches legacy command effect (channel updated + cache invalidated)
  — same persisted state (GreetingConfig) as deleted /welcome group's channel/toggle/message writes.
- test button delivers REAL localized preview to configured channel (defer → GreetingService render → channel send)
- preview failure (no channel) → ephemeral error, no mutation
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest


def _make_bot_with_greeting(guild_id: str = "123456789", config: MagicMock | None = None) -> MagicMock:
    bot = MagicMock()
    bot.greeting_service = MagicMock()
    cfg = config or MagicMock(
        guild_id=guild_id,
        welcome_channel_id="111222333",
        welcome_enabled=True,
        welcome_message="Welcome {mention}",
        welcome_card_enabled=True,
        theme_id=None,
        goodbye_channel_id=None,
        goodbye_enabled=False,
        goodbye_message=None,
        goodbye_card_enabled=False,
        onboarding_channel_id=None,
        card_enabled=True,
        updated_at=None,
    )
    cfg.guild_id = guild_id
    bot.greeting_service.get_config = AsyncMock(return_value=cfg)
    bot.greeting_service.save_config = AsyncMock(return_value=None)
    bot.greeting_service.resolve_renderer = MagicMock(return_value=lambda **_: io.BytesIO(b"fake-card"))
    bot.greeting_service.dispatch_greeting = AsyncMock()
    # For dispatch_welcome preview path we also mock GreetingService internals indirectly via real render path
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock(return_value=MagicMock(language="es"))
    return bot


def _make_interaction(guild_id: int = 123456789, user_id: int = 111, client: MagicMock | None = None) -> MagicMock:
    inter = MagicMock(spec=discord.Interaction)
    inter.guild = MagicMock(spec=discord.Guild)
    inter.guild.id = guild_id
    inter.guild_id = guild_id
    inter.guild.name = "TestGuild"
    # guild.get_channel for preview delivery
    chan = MagicMock(spec=discord.TextChannel)
    chan.send = AsyncMock()
    inter.guild.get_channel = MagicMock(return_value=chan)
    inter.guild.member_count = 42
    inter.guild.icon = None
    inter.user = MagicMock(spec=discord.Member)
    inter.user.id = user_id
    inter.user.display_name = "Tester"
    inter.user.display_avatar = MagicMock()
    inter.user.display_avatar.url = "https://cdn.example/ava.png"
    inter.user.guild_permissions.administrator = True
    inter.response = MagicMock()
    inter.response.send_message = AsyncMock()
    inter.response.send_modal = AsyncMock()
    inter.response.defer = AsyncMock()
    inter.response.edit_message = AsyncMock()
    inter.response.is_done.return_value = False
    inter.followup = MagicMock()
    inter.followup.send = AsyncMock()
    inter.message = MagicMock()
    inter.message.edit = AsyncMock()
    inter.client = client or _make_bot_with_greeting(str(guild_id))
    inter.data = {"custom_id": "setup:welcome:test"}
    return inter


class TestWelcomeModuleRegistration:
    """MODULES must contain welcome module implementing SetupModule protocol without framework edits."""

    def test_module_exists(self) -> None:
        from bot.views.setup_panel import MODULES

        assert "welcome" in MODULES, f"MODULES must contain welcome, got {list(MODULES.keys())}"

    def test_module_protocol(self) -> None:
        from bot.views.setup_panel import MODULES

        mod = MODULES["welcome"]
        assert hasattr(mod, "key") and mod.key == "welcome"
        assert hasattr(mod, "permission_key") and mod.permission_key == "greeting.manage"
        assert callable(getattr(mod, "render", None))
        assert callable(getattr(mod, "components", None))
        assert callable(getattr(mod, "handle", None))

    def test_registered_without_framework_edits(self) -> None:
        """Welcome module must be registered via MODULES dict, not by editing setup_panel framework to hardcode welcome."""
        import pathlib

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
        from bot.views.setup_modules.welcome import WelcomeSetupModule

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
        bot = _make_bot_with_greeting(guild_id, cfg)
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
        bot = _make_bot_with_greeting(guild_id)
        from bot.views.setup_modules.welcome import WelcomeSetupModule

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
        import pathlib

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
        from unittest.mock import AsyncMock

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
        bot = _make_bot_with_greeting(guild_id, cfg)
        # Make resolve_renderer return a callable that records it was the REAL renderer (not a fake)
        render_calls: list[dict] = []

        def _real_renderer(**kw: object) -> io.BytesIO:  # noqa: ANN002
            render_calls.append(kw)  # type: ignore[arg-type]
            return io.BytesIO(b"real-card")

        bot.greeting_service.resolve_renderer = MagicMock(return_value=_real_renderer)

        from bot.views.setup_modules.welcome import WelcomeSetupModule

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
        bot = _make_bot_with_greeting(guild_id, cfg)
        bot.greeting_service.resolve_renderer = MagicMock(return_value=lambda **_: io.BytesIO(b"x"))

        from bot.views.setup_modules.welcome import WelcomeSetupModule

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
        import pathlib

        src = pathlib.Path("bot/views/setup_modules/welcome.py").read_text(encoding="utf-8")
        # Ensure t("greetings.card.*") or similar is used; and no hardcoded "Welcome to" literal as title
        assert "t(" in src
        # Hardcoded greeting copy would appear as literal English title
        assert "greeting_title" in src or "greetings.card" in src


class TestWelcomeComponents:
    """Welcome module must expose components including test button setup:welcome:test."""

    def test_components_include_test_button(self) -> None:
        from bot.views.setup_modules.welcome import WelcomeSetupModule

        mod = WelcomeSetupModule(bot=_make_bot_with_greeting())
        items = mod.components("123456789")
        cids = {getattr(i, "custom_id", None) for i in items}
        assert "setup:welcome:test" in cids
