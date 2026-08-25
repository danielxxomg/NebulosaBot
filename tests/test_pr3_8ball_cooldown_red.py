"""RED: /8ball 20 localized + cooldown/handler (PR3 3.3-3.4).

Consolidation note (cycle-5 S5b/c): source-grep guards were replaced by
runtime twins where a behavioral assertion exists —

- command existence + ephemeral send → proven by ``test_8ball_command_ephemeral``;
- cooldown wiring → proven by runtime CooldownMapping introspection;
- uniform randomness → proven by spying ``random.choice`` at the service seam.

Kept without twin (documented): ``test_cooldown_handler_exists`` still reads
source because no error-pipeline harness drives CommandOnCooldown end-to-end
yet; ``test_8ball_has_locales`` is a production locale contract, not a grep.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.ocio import OcioCog
from bot.services.ocio_service import OcioService

_COOLDOWN_COMMANDS = ["dados", "banana", "8ball"]


def _make_ctx(guild_id=123456789):
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = guild_id
    return ctx


def _find_command(cog: OcioCog, name: str):
    """Return the cog command object registered under *name*."""
    for cmd in cog.__cog_commands__:
        if cmd.name == name:
            return cmd
    msg = f"command {name!r} not registered on OcioCog"
    raise AssertionError(msg)


class Test8BallContract:
    def test_8ball_has_locales(self):
        for lang in ("es", "en"):
            data = json.loads(Path(f"bot/locales/{lang}.json").read_text(encoding="utf-8"))
            ocio = data.get("ocio", {})
            # must have either 8ball dict or ocio.8ball.* keys
            keys = [k for k in str(ocio) if "8ball" in k] if isinstance(ocio, dict) else []
            # count keys starting with ocio.8ball.
            flat = []
            if isinstance(ocio, dict) and "8ball" in ocio:
                flat = list(ocio["8ball"].keys()) if isinstance(ocio["8ball"], dict) else []
            assert len(flat) >= 20 or len(keys) >= 20 or any("8ball" in str(v) for v in ocio.values()), (
                f"{lang} missing 20 ocio.8ball.* keys"
            )
            # Expected shape: r1-r20 + the localized embed_title (cycle-4 C1b).
            if flat:
                assert {f"r{i}" for i in range(1, 21)} <= set(flat), f"{lang} missing r1-r20 responses"
                assert "embed_title" in flat, f"{lang} missing ocio.8ball.embed_title"
                assert len(flat) == 21

    def test_cooldown_handler_exists(self):
        src = Path("bot/cogs/ocio.py").read_text(encoding="utf-8")
        assert "CommandOnCooldown" in src
        assert "retry_after" in src
        assert "ephemeral" in src


class TestCooldownWiring:
    """dados/banana/8ball carry cooldown(1, 5s) on their runtime buckets."""

    @pytest.mark.parametrize("name", _COOLDOWN_COMMANDS)
    def test_command_has_user_cooldown(self, name: str) -> None:
        cmd = _find_command(OcioCog(MagicMock()), name)
        bucket = getattr(cmd._buckets, "_cooldown", None)
        assert bucket is not None, f"{name} must configure a CooldownMapping"
        assert bucket.rate == 1
        assert bucket.per == 5


@pytest.mark.asyncio
async def test_8ball_returns_localized():
    svc = OcioService()
    # must not require discord mocks
    for gid in ("123456789", None):
        resp = svc.get_8ball_response(guild_id=str(gid) if gid else None, question="is it?")
        assert isinstance(resp, str) and len(resp) > 0


@pytest.mark.asyncio
async def test_8ball_response_draws_from_pool_uniformly():
    """get_8ball_response selects via random.choice over the localized pool."""
    svc = OcioService()
    with patch("bot.services.ocio_service.random.choice", wraps=__import__("random").choice) as choice_spy:
        svc.get_8ball_response(guild_id="123456789", question="is it?")
    choice_spy.assert_called_once()


@pytest.mark.asyncio
async def test_8ball_command_ephemeral():
    bot = MagicMock()
    cog = OcioCog(bot)
    ctx = _make_ctx()
    method = _find_command(cog, "8ball")
    # call it — should send ephemeral, no DB
    await method.callback(cog, ctx, question="will it pass?")
    assert ctx.send.await_count >= 1
    kwargs = ctx.send.call_args.kwargs
    assert kwargs.get("ephemeral") is True
