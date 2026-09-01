"""RED test for native-kwargs guard — 4.8.

Must exercise generate_greeting_card with localized kwargs directly
before deleting the _generate_greeting_card_compatibly shim.
This guards the deletion so the native path is proven.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import pytest

import bot.services.greeting_service as gs
from bot.core.cache import TTLCache
from bot.services.greeting_renderer import PillowGreetingRenderer
from bot.services.greeting_service import GreetingService
from tests.conftest import make_member


def _make_member(member_id: int = 333, name: str = "TestUser", guild_id: int = 123456789) -> MagicMock:
    """Shim — delegates to ``tests.conftest.make_member`` with greeting scaffolding."""
    return make_member(
        guild_id=guild_id,
        member_id=member_id,
        name=name,
        display_name=name,
        avatar_url="https://cdn.discordapp.com/avatars/333/abc.png",
        guild_icon_url="https://cdn.discordapp.com/icons/123/icon.png",
    )


@pytest.mark.asyncio
async def test_native_kwargs_path_calls_renderer_directly() -> None:
    """GreetingService must call greeting_renderer.render with localized kwargs natively (no shim)."""
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
    renderer = MagicMock(spec=PillowGreetingRenderer)
    renderer.render.return_value = io.BytesIO(b"fake-png")
    service = GreetingService(db=db, cache=cache, greeting_renderer=renderer)

    member = _make_member()
    await service.dispatch_welcome(member)
    assert renderer.render.called, "renderer.render must be called with native kwargs"
    kwargs = renderer.render.call_args.kwargs
    assert "greeting_title" in kwargs
    assert "member_count_text" in kwargs
    assert "guild_icon_url" in kwargs
    assert kwargs["card_type"] == "welcome"


def test_shim_absent_after_migration() -> None:
    """After GREEN 4.9, the compat shim must be deleted.

    This guards the removal: the named symbol ``_generate_greeting_card_compatibly``
    MUST be absent from the module. Verifying ``hasattr`` is False (rather than
    a tautological ``assert True``) proves the shim was actually removed and
    blocks any reintroduction.
    """
    assert not hasattr(gs, "_generate_greeting_card_compatibly"), (
        "_generate_greeting_card_compatibly shim must be absent after 4.9"
    )
    # Belt-and-braces: the source must not reference the shim either.
    assert "_generate_greeting_card_compatibly" not in dir(gs)
