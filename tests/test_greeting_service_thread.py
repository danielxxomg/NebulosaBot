"""WG-4: dispatch_greeting MUST wrap the renderer call in asyncio.to_thread (RED if removed)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.core.cache import TTLCache
from bot.services.greeting_renderer import PillowGreetingRenderer
from bot.services.greeting_service import GreetingService


def _make_member() -> MagicMock:
    """Build a mock discord.Member whose guild exposes a sendable channel."""
    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_channel.send = AsyncMock(return_value=None)
    guild = MagicMock()
    guild.id = 123456789
    guild.name = "TestServer"
    guild.member_count = 150
    guild.get_channel.return_value = mock_channel
    guild.icon = None
    avatar = MagicMock()
    avatar.url = "https://cdn.discordapp.com/avatars/333/abc.png"
    member = MagicMock(spec=discord.Member)
    member.id = 333
    member.name = "ThreadUser"
    member.display_name = "ThreadUser"
    member.display_avatar = avatar
    member.guild = guild
    member.mention = "<@333>"
    return member


@pytest.mark.asyncio
async def test_dispatch_greeting_runs_renderer_through_to_thread() -> None:
    """The renderer callable MUST be handed to asyncio.to_thread."""
    db = AsyncMock()
    db.get_greeting_config.return_value = {
        "guildId": "123456789",
        "welcomeEnabled": True,
        "welcomeChannelId": "111111111",
        "welcomeCardEnabled": True,
        "welcomeMessage": "Welcome {mention}!",
        "goodbyeEnabled": False,
    }
    cache = TTLCache()
    renderer = PillowGreetingRenderer()
    service = GreetingService(db=db, cache=cache, greeting_renderer=renderer)

    captured: list[object] = []
    real_to_thread = asyncio.to_thread

    async def _recorder(func, *args, **kwargs):
        captured.append(func)
        return await real_to_thread(func, *args, **kwargs)

    member = _make_member()
    with (
        patch("bot.services.greeting_service.asyncio.to_thread", side_effect=_recorder),
        patch("bot.services.shared_assets._safe_fetch_avatar", return_value=None),
    ):
        await service.dispatch_welcome(member)

    assert captured, "asyncio.to_thread was not awaited — renderer ran inline (WG-4 regression)"
    # Bound methods are freshly constructed per attribute access; compare by
    # equality + __self__ identity (not `is`) to pin THIS renderer.
    handed = captured[0]
    assert callable(handed) and getattr(handed, "__self__", None) is renderer
    assert handed == renderer.render, "to_thread must receive renderer.render (not a direct call)"
    channel = member.guild.get_channel.return_value
    assert channel.send.await_count == 1
    sent = channel.send.call_args.kwargs.get("file")
    assert isinstance(sent, discord.File)
    assert sent.filename == "welcome.png"
