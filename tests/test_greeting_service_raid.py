"""S4.3 — raid saturation guard for GreetingService.dispatch_greeting.

A join raid bursts N concurrent greetings; unbounded concurrent Pillow
renders saturate CPU/threads. Design D4 chose a guild-scoped
``asyncio.Semaphore(2)`` with NON-BLOCKING acquire over time-window
debounce: renders beyond the cap are dropped (never queued) with a
WARNING log.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.cache import TTLCache
from bot.services.greeting_service import GreetingService

_GUILD_ID = 123456789


class _CountingRenderer:
    """Renderer protocol stand-in tracking concurrent render executions."""

    def __init__(self, sleep_s: float = 0.05) -> None:
        self.sleep_s = sleep_s
        self.active = 0
        self.peak = 0
        self.calls = 0

    def render(self, **_kwargs: object) -> io.BytesIO:
        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        time.sleep(self.sleep_s)
        self.active -= 1
        return io.BytesIO(b"fake-png")


def _make_member(guild_id: int = _GUILD_ID) -> MagicMock:
    """Build a mock discord.Member whose guild exposes a sendable channel."""
    mock_channel = MagicMock(spec=discord.TextChannel)
    mock_channel.send = AsyncMock(return_value=None)
    guild = MagicMock()
    guild.id = guild_id
    guild.name = f"Guild{guild_id}"
    guild.member_count = 150
    guild.get_channel.return_value = mock_channel
    guild.icon = None
    avatar = MagicMock()
    avatar.url = f"https://cdn.discordapp.com/avatars/333/{guild_id}.png"
    member = MagicMock(spec=discord.Member)
    member.id = 333
    member.name = "RaidUser"
    member.display_name = "RaidUser"
    member.display_avatar = avatar
    member.guild = guild
    member.mention = "<@333>"
    return member


def _make_service(renderer: _CountingRenderer) -> tuple[GreetingService, AsyncMock]:
    """Return a GreetingService wired to an enabled welcome config."""
    db = AsyncMock()
    db.get_greeting_config.return_value = {
        "guildId": str(_GUILD_ID),
        "welcomeEnabled": True,
        "welcomeChannelId": "111111111",
        "welcomeCardEnabled": True,
        "welcomeMessage": "Welcome {mention}!",
        "goodbyeEnabled": False,
    }
    service = GreetingService(db=db, cache=TTLCache(), greeting_renderer=renderer)
    return service, db


class TestRaidSaturationSemaphore:
    """D4 — Semaphore(2) caps concurrent renders per guild; excess drops."""

    @pytest.mark.asyncio
    async def test_burst_caps_concurrency_and_drops_excess(self, caplog: pytest.LogCaptureFixture) -> None:
        renderer = _CountingRenderer()
        service, _db = _make_service(renderer)

        members = [_make_member() for _ in range(6)]
        with caplog.at_level(logging.WARNING, logger="bot.services.greeting_service"):
            await asyncio.gather(*(service.dispatch_welcome(m) for m in members))

        # Exactly 2 renders ever overlapped.
        assert renderer.peak == 2, f"expected peak concurrency 2, saw {renderer.peak}"
        assert renderer.calls == 2, "saturated dispatches must be dropped BEFORE rendering"
        # Only the admitted dispatches reached Discord.
        sent_counts = [m.guild.get_channel.return_value.send.await_count for m in members]
        assert sum(sent_counts) == 2
        # Each excess join produced exactly one saturation warning.
        drops = [r for r in caplog.records if "greeting dropped: raid saturation" in r.getMessage()]
        assert len(drops) == 4
        assert all(f"guild={_GUILD_ID}" in r.getMessage() for r in drops)

    @pytest.mark.asyncio
    async def test_after_release_new_dispatch_is_admitted(self) -> None:
        """Once a slot frees, subsequent joins are NOT stuck dropped."""
        renderer = _CountingRenderer(sleep_s=0.01)
        service, _db = _make_service(renderer)
        # First wave saturates: 2 admitted, rest dropped.
        await asyncio.gather(*(service.dispatch_welcome(_make_member()) for _ in range(4)))
        admitted_first_wave = renderer.calls
        assert admitted_first_wave == 2
        # A later lone join must render again.
        await service.dispatch_welcome(_make_member())
        assert renderer.calls == admitted_first_wave + 1

    @pytest.mark.asyncio
    async def test_semaphore_is_guild_scoped(self) -> None:
        """Saturation in one guild never drops another guild's greetings."""
        renderer = _CountingRenderer()
        db = AsyncMock()
        db.get_greeting_config.return_value = {
            "guildId": "1",
            "welcomeEnabled": True,
            "welcomeChannelId": "111111111",
            "welcomeCardEnabled": True,
            "welcomeMessage": "hi",
            "goodbyeEnabled": False,
        }
        service = GreetingService(db=db, cache=TTLCache(), greeting_renderer=renderer)

        busy = [_make_member(guild_id=999) for _ in range(4)]
        other = _make_member(guild_id=777)
        await asyncio.gather(
            *(service.dispatch_welcome(m) for m in busy),
            service.dispatch_welcome(other),
        )
        # The unrelated guild's card was rendered and sent.
        assert other.guild.get_channel.return_value.send.await_count == 1
