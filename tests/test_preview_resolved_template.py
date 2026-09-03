"""Remediation RED tests — verify-report CRITICAL #2 (PREVIEW-CONTRACT).

The ``_handle_test`` preview path must forward the RESOLVED per-kind
template id (``select_template`` fallback chain result) to the renderer as
both ``template_id`` and the legacy ``theme_id`` alias, and tests must
prove the resolved value flows through end-to-end.

Ref: openspec/changes/greeting-templates/verify-report.md CRITICAL #2 and
setup-panel spec "Preview forwards resolved per-kind template".
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.greeting_service import select_template

_WELCOME_SELECT_ID = "setup:welcome:select_template"
_GOODBYE_SELECT_ID = "setup:goodbye:select_template"


def _preview_bot(
    guild_id: str,
    *,
    welcome_template_id: str | None,
    goodbye_template_id: str | None,
    theme_id: str | None,
    card_enabled: bool = True,
) -> MagicMock:
    bot = MagicMock()
    bot.greeting_service = MagicMock()
    cfg = MagicMock(
        guild_id=guild_id,
        welcome_channel_id="111222333",
        goodbye_channel_id="222333444",
        welcome_enabled=True,
        goodbye_enabled=True,
        welcome_message="Hola {mention}",
        goodbye_message="Chau {mention}",
        welcome_card_enabled=card_enabled,
        goodbye_card_enabled=card_enabled,
        welcome_template_id=welcome_template_id,
        goodbye_template_id=goodbye_template_id,
        theme_id=theme_id,
        onboarding_channel_id=None,
    )
    cfg.guild_id = guild_id
    bot.greeting_service.get_config = AsyncMock(return_value=cfg)
    bot.greeting_service.save_config = AsyncMock(return_value=None)
    return bot


def _preview_interaction(guild_id: int, bot: MagicMock, custom_id: str) -> MagicMock:
    inter = MagicMock(spec=discord.Interaction)
    inter.guild = MagicMock(spec=discord.Guild)
    inter.guild.id = guild_id
    inter.guild.name = "TestGuild"
    inter.guild.member_count = 42
    inter.guild.icon = None
    chan = MagicMock(spec=discord.TextChannel)
    chan.send = AsyncMock()
    inter.guild.get_channel = MagicMock(return_value=chan)
    inter.user = MagicMock(spec=discord.Member)
    inter.user.id = 111
    inter.user.display_name = "Tester"
    inter.user.display_avatar = MagicMock()
    inter.user.display_avatar.url = "https://cdn.example/ava.png"
    inter.user.guild_permissions.administrator = True
    inter.response = MagicMock()
    inter.response.defer = AsyncMock()
    inter.followup = MagicMock()
    inter.followup.send = AsyncMock()
    inter.data = {"custom_id": custom_id}
    inter.client = bot
    return inter


class TestResolvedPreviewWelcome:
    """Welcome preview forwards the resolved per-kind template id end-to-end."""

    @pytest.mark.asyncio
    async def test_preview_forwards_resolved_template_and_alias(self) -> None:
        """welcome_template_id='sunset_wave' → renderer gets template_id AND theme_id='sunset_wave'."""
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # documented-exception: facade indirection

        guild_id = "123456789"
        bot = _preview_bot(
            guild_id,
            welcome_template_id="sunset_wave",
            goodbye_template_id=None,
            theme_id="gaming_neon",
        )
        render_calls: list[dict] = []

        def _real_renderer(**kw: object) -> io.BytesIO:  # noqa: ANN002
            render_calls.append(kw)
            return io.BytesIO(b"resolved-card")

        bot.greeting_service.resolve_renderer = MagicMock(return_value=_real_renderer)

        mod = WelcomeSetupModule(bot=bot)
        interaction = _preview_interaction(int(guild_id), bot, "setup:welcome:test")
        await mod.handle(interaction, "test")

        assert render_calls, "renderer must have been invoked"
        kwargs = render_calls[0]
        assert kwargs.get("template_id") == "sunset_wave", (
            f"welcome preview must forward resolved template_id, got {kwargs.get('template_id')!r}"
        )
        assert kwargs.get("theme_id") == "sunset_wave", (
            f"welcome preview must forward theme_id=resolved alias, got {kwargs.get('theme_id')!r}"
        )

    @pytest.mark.asyncio
    async def test_preview_unknown_template_resolves_default_with_no_raise(self) -> None:
        """Unknown stored id → select_template resolves 'default'; default card renders."""
        from bot.views.setup_modules.welcome import WelcomeSetupModule  # documented-exception: facade indirection

        guild_id = "123456789"
        bot = _preview_bot(
            guild_id,
            welcome_template_id="unknown_xyz",
            goodbye_template_id=None,
            theme_id=None,
        )
        render_calls: list[dict] = []

        def _real_renderer(**kw: object) -> io.BytesIO:  # noqa: ANN002
            render_calls.append(kw)
            return io.BytesIO(b"default-card")

        bot.greeting_service.resolve_renderer = MagicMock(return_value=_real_renderer)

        mod = WelcomeSetupModule(bot=bot)
        interaction = _preview_interaction(int(guild_id), bot, "setup:welcome:test")
        await mod.handle(interaction, "test")

        assert render_calls, "renderer must still be invoked for unknown id"
        kwargs = render_calls[0]
        assert kwargs.get("template_id") == "default", (
            f"unknown stored id must resolve to default, got {kwargs.get('template_id')!r}"
        )
        assert kwargs.get("theme_id") == "default"
        interaction.followup.send.assert_awaited()  # preview_success ephemeral

    @pytest.mark.asyncio
    async def test_welcome_wins_over_legacy_theme_id(self) -> None:
        """Per-kind welcome id wins over legacy theme_id in the resolution chain."""
        cfg = MagicMock(
            welcome_template_id="sunset_wave",
            goodbye_template_id=None,
            theme_id="gaming_neon",
        )
        assert select_template(cfg, "welcome") == "sunset_wave"


class TestResolvedPreviewGoodbye:
    """Goodbye preview forwards its own resolved per-kind template id."""

    @pytest.mark.asyncio
    async def test_preview_forwards_resolved_template_and_alias(self) -> None:
        """goodbye_template_id='minimal_light' → renderer gets template_id AND theme_id='minimal_light'."""
        from bot.views.setup_modules.goodbye import GoodbyeSetupModule  # documented-exception: facade indirection

        guild_id = "123456789"
        bot = _preview_bot(
            guild_id,
            welcome_template_id="sunset_wave",
            goodbye_template_id="minimal_light",
            theme_id="gaming_neon",
        )
        render_calls: list[dict] = []

        def _real_renderer(**kw: object) -> io.BytesIO:  # noqa: ANN002
            render_calls.append(kw)
            return io.BytesIO(b"resolved-goodbye-card")

        bot.greeting_service.resolve_renderer = MagicMock(return_value=_real_renderer)

        mod = GoodbyeSetupModule(bot=bot)
        interaction = _preview_interaction(int(guild_id), bot, "setup:goodbye:test")
        await mod.handle(interaction, "test")

        assert render_calls, "renderer must have been invoked"
        kwargs = render_calls[0]
        assert kwargs.get("template_id") == "minimal_light", (
            f"goodbye preview must forward resolved template_id, got {kwargs.get('template_id')!r}"
        )
        assert kwargs.get("theme_id") == "minimal_light", (
            f"goodbye preview must forward theme_id=resolved alias, got {kwargs.get('theme_id')!r}"
        )

    @pytest.mark.asyncio
    async def test_goodbye_preview_independent_from_welcome(self) -> None:
        """Kinds resolve independently — goodbye resolution never uses welcome's id."""
        cfg = MagicMock(
            welcome_template_id="sunset_wave",
            goodbye_template_id="minimal_light",
            theme_id="gaming_neon",
        )
        assert select_template(cfg, "goodbye") == "minimal_light"
        assert select_template(cfg, "welcome") == "sunset_wave"
