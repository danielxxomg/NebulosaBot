"""WG-4: dispatch_greeting MUST wrap the renderer call in asyncio.to_thread (RED if removed)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.core.cache import TTLCache
from bot.services.greeting_renderer import PillowGreetingRenderer
from bot.services.greeting_service import GreetingService
from tests.conftest import make_member


def _make_member() -> MagicMock:
    """Zero-arg shim — delegates to conftest with fixed greeting defaults."""
    return make_member(
        guild_id=123456789,
        member_id=333,
        display_name="ThreadUser",
        name="ThreadUser",
    )


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


@pytest.mark.asyncio
async def test_dispatch_greeting_passes_theme_id_through_to_thread() -> None:
    """PR1 3.2 — config.theme_id is forwarded to the renderer via asyncio.to_thread."""
    db = AsyncMock()
    db.get_greeting_config.return_value = {
        "guildId": "123456789",
        "welcomeEnabled": True,
        "welcomeChannelId": "111111111",
        "welcomeCardEnabled": True,
        "welcomeMessage": "Welcome {mention}!",
        "goodbyeEnabled": False,
        "themeId": "gaming_neon",
    }
    cache = TTLCache()
    renderer = PillowGreetingRenderer()
    service = GreetingService(db=db, cache=cache, greeting_renderer=renderer)

    captured_kwargs: list[dict] = []
    real_to_thread = asyncio.to_thread

    async def _recorder(func, *args, **kwargs):
        captured_kwargs.append(kwargs)
        return await real_to_thread(func, *args, **kwargs)

    member = _make_member()
    with (
        patch("bot.services.greeting_service.asyncio.to_thread", side_effect=_recorder),
        patch("bot.services.shared_assets._safe_fetch_avatar", return_value=None),
    ):
        await service.dispatch_welcome(member)

    assert captured_kwargs, "asyncio.to_thread was not awaited"
    # The renderer call MUST include theme_id from the config.
    render_kwargs = next(
        (kw for kw in captured_kwargs if "card_type" in kw and "username" in kw),
        None,
    )
    assert render_kwargs is not None, "no render call captured in to_thread"
    assert render_kwargs.get("theme_id") == "gaming_neon", (
        f"theme_id not forwarded through to_thread: {render_kwargs.get('theme_id')}"
    )


@pytest.mark.asyncio
async def test_dispatch_greeting_passes_none_theme_id_for_default() -> None:
    """PR1 3.2 — a config with no theme_id forwards None to the renderer."""
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

    captured_kwargs: list[dict] = []
    real_to_thread = asyncio.to_thread

    async def _recorder(func, *args, **kwargs):
        captured_kwargs.append(kwargs)
        return await real_to_thread(func, *args, **kwargs)

    member = _make_member()
    with (
        patch("bot.services.greeting_service.asyncio.to_thread", side_effect=_recorder),
        patch("bot.services.shared_assets._safe_fetch_avatar", return_value=None),
    ):
        await service.dispatch_welcome(member)

    render_kwargs = next(
        (kw for kw in captured_kwargs if "card_type" in kw and "username" in kw),
        None,
    )
    assert render_kwargs is not None
    assert render_kwargs.get("theme_id") is None, (
        f"default config must forward theme_id=None: {render_kwargs.get('theme_id')}"
    )
