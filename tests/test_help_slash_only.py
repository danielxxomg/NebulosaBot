"""S6A.2 guard — help renders slash syntax only and deprecation-invariant holds."""

from __future__ import annotations

import pathlib


def test_help_no_prefix_example() -> None:
    """Help builder and cog must not contain prefix examples.

    Slash-only invariant: ``/help`` output and its builder never render a
    text prefix. ``SLASH_DESCRIPTIONS`` is data, not a prefix marker — but
    ``nb!`` and ``[prefix`` substrings are still forbidden as invocation text.
    """
    src = pathlib.Path("bot/cogs/core.py").read_text(encoding="utf-8")
    assert "[prefix" not in src, "prefix marker reintroduced in help"
    assert "nb!" not in src, "nb! prefix reintroduced in help builder"
    # Also assert no '!' invocation remains in slash help values
    # (Slash field values are checked via _build_cog_help_embed in test_core_help_builder;
    # here we pin the source does not emit prefix examples.)


def test_build_cog_help_embed_slash_only() -> None:
    """Real ``_build_cog_help_embed`` slash-only output — no '!' in any field value."""
    from unittest.mock import MagicMock

    from bot.cogs.core import _build_cog_help_embed

    cmd = MagicMock()
    cmd.name = "ping"
    cmd.qualified_name = "ping"
    cmd.description = "Check latency"
    cmd.hidden = False
    cog = MagicMock()
    cog.get_commands.return_value = [cmd]
    bot = MagicMock()
    bot.get_cog.return_value = cog
    bot.cogs = {"Core": cog}
    embed = _build_cog_help_embed(bot, "Core", guild_id=None)
    assert embed is not None
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "`/ping`"
    val = embed.fields[0].value or ""
    assert "!" not in val, "help value must not contain '!' prefix syntax"
    assert "!" not in (embed.description or ""), "help description must not contain prefix marker"
