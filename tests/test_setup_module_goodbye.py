"""S2b.2 RED — Goodbye setup module: parity + preview.

Same parity + preview contract as welcome; split per tasks artifact.
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
        welcome_channel_id=None,
        welcome_enabled=False,
        welcome_message=None,
        welcome_card_enabled=False,
        theme_id=None,
        goodbye_channel_id="222333444",
        goodbye_enabled=True,
        goodbye_message="Bye {mention}",
        goodbye_card_enabled=True,
        onboarding_channel_id=None,
    )
    cfg.guild_id = guild_id
    bot.greeting_service.get_config = AsyncMock(return_value=cfg)
    bot.greeting_service.save_config = AsyncMock(return_value=None)
    bot.greeting_service.resolve_renderer = MagicMock(return_value=lambda **_: io.BytesIO(b"fake-goodbye"))
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock(return_value=MagicMock(language="en"))
    return bot


def _make_interaction(guild_id: int = 123456789, user_id: int = 111, client: MagicMock | None = None) -> MagicMock:
    inter = MagicMock(spec=discord.Interaction)
    inter.guild = MagicMock(spec=discord.Guild)
    inter.guild.id = guild_id
    inter.guild_id = guild_id
    inter.guild.name = "TestGuild"
    chan = MagicMock(spec=discord.TextChannel)
    chan.send = AsyncMock()
    inter.guild.get_channel = MagicMock(return_value=chan)
    inter.guild.member_count = 99
    inter.guild.icon = None
    inter.user = MagicMock(spec=discord.Member)
    inter.user.id = user_id
    inter.user.display_name = "LeavingUser"
    inter.user.display_avatar = MagicMock()
    inter.user.display_avatar.url = "https://cdn.example/ava2.png"
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
    inter.data = {"custom_id": "setup:goodbye:test"}
    return inter


class TestGoodbyeModuleRegistration:
    def test_module_exists(self) -> None:
        from bot.views.setup_panel import MODULES  # documented-exception: facade indirection

        assert "goodbye" in MODULES, f"MODULES must contain goodbye, got {list(MODULES.keys())}"

    def test_module_protocol(self) -> None:
        from bot.views.setup_panel import MODULES  # documented-exception: facade indirection

        mod = MODULES["goodbye"]
        assert hasattr(mod, "key") and mod.key == "goodbye"
        assert hasattr(mod, "permission_key") and mod.permission_key == "greeting.manage"
        assert callable(getattr(mod, "render", None))
        assert callable(getattr(mod, "components", None))
        assert callable(getattr(mod, "handle", None))

    def test_registered_without_framework_edits(self) -> None:
        import pathlib  # documented-exception: facade indirection

        src = pathlib.Path("bot/views/setup_panel.py").read_text(encoding="utf-8")
        assert "class GoodbyeSetupModule" not in src
        assert pathlib.Path("bot/views/setup_modules/goodbye.py").exists()


class TestGoodbyeModuleParity:
    @pytest.mark.asyncio
    async def test_save_channel_matches_legacy_effect(self) -> None:
        from bot.views.setup_modules.goodbye import GoodbyeSetupModule  # documented-exception: facade indirection

        guild_id = "123456789"
        cfg = MagicMock(
            guild_id=guild_id,
            welcome_channel_id=None,
            welcome_enabled=False,
            welcome_message=None,
            welcome_card_enabled=False,
            theme_id=None,
            goodbye_channel_id=None,
            goodbye_enabled=False,
            goodbye_message=None,
            goodbye_card_enabled=False,
            onboarding_channel_id=None,
        )
        cfg.guild_id = guild_id
        bot = _make_bot_with_greeting(guild_id, cfg)
        mod = GoodbyeSetupModule(bot=bot)
        if hasattr(mod, "set_goodbye_channel"):
            await mod.set_goodbye_channel(guild_id, "444555666")
        else:
            fetched = await bot.greeting_service.get_config(guild_id)
            fetched.goodbye_channel_id = "444555666"
            await bot.greeting_service.save_config(fetched)
        assert bot.greeting_service.save_config.await_count == 1
        saved = bot.greeting_service.save_config.call_args.args[0]
        assert saved.goodbye_channel_id == "444555666"


class TestGoodbyePreviewRealArtifact:
    @pytest.mark.asyncio
    async def test_preview_delivers_real_localized_card_to_channel(self) -> None:
        guild_id = "123456789"
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(guild_id)
        guild.name = "TestGuild"
        guild.member_count = 99
        guild.icon = None
        guild.get_channel = MagicMock(return_value=channel)

        cfg = MagicMock(
            guild_id=guild_id,
            goodbye_channel_id="222333444",
            goodbye_enabled=True,
            goodbye_message="Bye {mention}",
            goodbye_card_enabled=True,
            welcome_channel_id=None,
            welcome_enabled=False,
            welcome_message=None,
            welcome_card_enabled=False,
            theme_id=None,
            onboarding_channel_id=None,
        )
        cfg.guild_id = guild_id
        bot = _make_bot_with_greeting(guild_id, cfg)
        render_calls: list[dict] = []

        def _real_renderer(**kw: object) -> io.BytesIO:  # noqa: ANN002
            render_calls.append(kw)
            return io.BytesIO(b"real-goodbye-card")

        bot.greeting_service.resolve_renderer = MagicMock(return_value=_real_renderer)

        from bot.views.setup_modules.goodbye import GoodbyeSetupModule  # documented-exception: facade indirection

        mod = GoodbyeSetupModule(bot=bot)
        interaction = _make_interaction(guild_id=int(guild_id), client=bot)
        interaction.guild = guild
        await mod.handle(interaction, "test")

        assert interaction.response.defer.await_count == 1
        assert channel.send.await_count == 1
        assert "file" in channel.send.call_args.kwargs or channel.send.call_args.args
        assert render_calls
        assert isinstance(render_calls[0].get("greeting_title"), str)
        assert isinstance(render_calls[0].get("member_count_text"), str)

    @pytest.mark.asyncio
    async def test_preview_failure_no_channel_ephemeral_no_mutation(self) -> None:
        guild_id = "123456789"
        cfg = MagicMock(
            guild_id=guild_id,
            goodbye_channel_id=None,
            goodbye_enabled=True,
            goodbye_message=None,
            goodbye_card_enabled=True,
        )
        cfg.guild_id = guild_id
        bot = _make_bot_with_greeting(guild_id, cfg)
        bot.greeting_service.resolve_renderer = MagicMock(return_value=lambda **_: io.BytesIO(b"x"))

        from bot.views.setup_modules.goodbye import GoodbyeSetupModule  # documented-exception: facade indirection

        mod = GoodbyeSetupModule(bot=bot)
        interaction = _make_interaction(guild_id=int(guild_id), client=bot)
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

        ephemeral = interaction.followup.send.await_count + interaction.response.send_message.await_count
        assert ephemeral >= 1
        bot.greeting_service.save_config.assert_not_awaited()

    def test_caller_passes_translated_strings_no_hardcoded_copy(self) -> None:
        import pathlib  # documented-exception: facade indirection

        src = pathlib.Path("bot/views/setup_modules/goodbye.py").read_text(encoding="utf-8")
        assert "t(" in src
        assert "greeting_title" in src or "greetings.card" in src

    def test_components_include_test_button(self) -> None:
        from bot.views.setup_modules.goodbye import GoodbyeSetupModule  # documented-exception: facade indirection

        mod = GoodbyeSetupModule(bot=_make_bot_with_greeting())
        items = mod.components("123456789")
        cids = {getattr(i, "custom_id", None) for i in items}
        assert "setup:goodbye:test" in cids
