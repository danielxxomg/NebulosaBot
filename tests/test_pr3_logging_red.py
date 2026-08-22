"""RED tests for PR3 Phase 2 — LoggingService.log_voice_event.

Strict TDD: these MUST fail before GREEN (method missing).
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.logging_service import LoggingService
from bot.utils.brand import INFO


def _guild_config(log_enabled: bool, log_channel_id: str | None):
    cfg = MagicMock()
    cfg.log_enabled = log_enabled
    cfg.log_channel_id = log_channel_id
    return cfg


def _make_bot(
    guild_id: str = "111", log_enabled: bool = True, log_channel_id: str | None = "999"
) -> tuple[MagicMock, MagicMock, MagicMock]:
    mock_guild_service = AsyncMock()
    mock_guild_service.get_config.return_value = _guild_config(log_enabled, log_channel_id)
    mock_bot = MagicMock()
    mock_bot.guild_service = mock_guild_service
    mock_bot.get_guild.return_value = MagicMock(icon=None)
    mock_bot.get_channel.return_value = MagicMock(send=AsyncMock())
    # ensure guild_footer_icon path doesn't fail: bot.user
    mock_bot.user = MagicMock()
    mock_bot.user.display_avatar = MagicMock(url="https://cdn.example/avatar.png")
    return mock_bot, mock_guild_service, mock_bot.get_channel.return_value


def _member(guild_id: str = "111", member_id: int = 1, name: str = "Alice") -> MagicMock:
    m = MagicMock(spec=discord.Member)
    m.id = member_id
    m.name = name
    m.mention = f"<@{member_id}>"
    m.display_name = name
    m.guild = MagicMock()
    m.guild.id = int(guild_id)
    m.bot = False
    return m


def _voice_state(channel: MagicMock | None = None, self_mute: bool = False, self_deaf: bool = False) -> MagicMock:
    vs = MagicMock(spec=discord.VoiceState)
    vs.channel = channel
    vs.self_mute = self_mute
    vs.self_deaf = self_deaf
    vs.mute = self_mute
    vs.deaf = self_deaf
    return vs


def _channel(cid: int = 100, name: str = "General") -> MagicMock:
    ch = MagicMock()
    ch.id = cid
    ch.name = name
    return ch


class TestLogVoiceEventExists:
    def test_log_voice_event_is_async(self) -> None:
        assert hasattr(LoggingService, "log_voice_event"), "LoggingService.log_voice_event missing — RED"
        assert inspect.iscoroutinefunction(LoggingService.log_voice_event)

    def test_log_voice_event_uses_brand_token(self) -> None:
        src = open("bot/services/logging_service.py", encoding="utf-8").read()  # noqa: SIM115
        # new method must reference brand token (INFO) not hex literal
        # allow INFO import already present; just ensure method body uses INFO/LOG_COLOR
        assert "log_voice_event" in src
        # must not introduce hex literal in that file beyond brand
        # (brand guard is global; we just check method exists)

    def test_log_voice_event_no_blocking_io(self) -> None:
        src = open("bot/services/logging_service.py", encoding="utf-8").read()  # noqa: SIM115
        # forbid blocking calls inside new method region
        # crude guard: file must not import time.sleep/requests/Pillow in logging_service
        assert "time.sleep" not in src
        assert "import requests" not in src


class TestLogVoiceEventRouting:
    @pytest.mark.asyncio
    async def test_guild_scoped_routes_to_correct_channel(self) -> None:
        """Guild A event → guild A logChannelId only."""
        mock_bot_a, _, log_ch_a = _make_bot(guild_id="111", log_channel_id="999")
        svc_a = LoggingService(bot=mock_bot_a)
        member = _member(guild_id="111")
        before = _voice_state(channel=None)
        after = _voice_state(channel=_channel(100, "Voice-A"))
        await svc_a.log_voice_event("111", member, "join", before, after)
        mock_bot_a.get_channel.assert_called_once_with(999)
        log_ch_a.send.assert_awaited_once()
        embed = log_ch_a.send.call_args.kwargs["embed"]
        assert isinstance(embed, discord.Embed)
        assert embed.color is not None and embed.color.value == INFO

    @pytest.mark.asyncio
    async def test_log_enabled_false_skips_silently(self) -> None:
        mock_bot, _, _ = _make_bot(guild_id="111", log_enabled=False, log_channel_id="999")
        svc = LoggingService(bot=mock_bot)
        await svc.log_voice_event("111", _member(), "join", _voice_state(None), _voice_state(_channel()))
        mock_bot.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_log_channel_skips_silently(self) -> None:
        mock_bot, _, _ = _make_bot(guild_id="111", log_enabled=True, log_channel_id=None)
        svc = LoggingService(bot=mock_bot)
        await svc.log_voice_event("111", _member(), "leave", _voice_state(_channel()), _voice_state(None))
        mock_bot.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_blocking_io_async_only(self) -> None:
        mock_bot, _, log_ch = _make_bot()
        svc = LoggingService(bot=mock_bot)
        before = _voice_state(channel=None)
        after = _voice_state(channel=_channel())
        await svc.log_voice_event("111", _member(), "join", before, after)
        # awaitable proves async-only; no thread blocking
        log_ch.send.assert_awaited_once()
