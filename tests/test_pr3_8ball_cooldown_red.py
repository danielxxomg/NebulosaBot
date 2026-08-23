"""RED: /8ball 20 localized + cooldown/handler (PR3 3.3-3.4)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from bot.cogs.ocio import OcioCog


def _make_ctx(guild_id=123456789):
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = guild_id
    return ctx


class Test8BallExists:
    def test_has_8ball_command(self):
        assert (
            hasattr(OcioCog, "eight_ball")
            or hasattr(OcioCog, "eightball")
            or any(
                getattr(m, "__name__", "") in ("8ball", "eight_ball", "eightball") for m in OcioCog.__dict__.values()
            )
            or any("8ball" in str(v) for v in OcioCog.__dict__.values())
        )

    def test_8ball_has_locales(self):
        import json

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

    def test_8ball_ephemeral_no_db(self):
        src = Path("bot/cogs/ocio.py").read_text(encoding="utf-8")
        # 8ball command should be present
        assert "8ball" in src.lower()
        # ephemereral send
        assert "ephemeral" in src

    def test_cooldown_on_three_commands(self):
        src = Path("bot/cogs/ocio.py").read_text(encoding="utf-8")
        # each of dados/banana/8ball must carry cooldown
        assert src.count("cooldown(1, 5") >= 3 or src.count("cooldown(1,5") >= 3
        assert "BucketType.user" in src

    def test_cooldown_handler_exists(self):
        src = Path("bot/cogs/ocio.py").read_text(encoding="utf-8")
        assert "CommandOnCooldown" in src
        assert "retry_after" in src
        assert "ephemeral" in src

    def test_8ball_uniform_random(self):
        # service get_8ball_response uses random.choice uniform
        from bot.services.ocio_service import OcioService

        assert hasattr(OcioService, "get_8ball_response") or hasattr(OcioService, "get_eight_ball_response")
        src = Path("bot/services/ocio_service.py").read_text(encoding="utf-8")
        assert "random.choice" in src or "random.randint" in src


@pytest.mark.asyncio
async def test_8ball_returns_localized():
    from bot.services.ocio_service import OcioService

    svc = OcioService()
    # must not require discord mocks
    for gid in ("123456789", None):
        resp = svc.get_8ball_response(guild_id=str(gid) if gid else None, question="is it?")
        assert isinstance(resp, str) and len(resp) > 0


@pytest.mark.asyncio
async def test_8ball_command_ephemeral():
    import warnings

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    bot = MagicMock()
    cog = OcioCog(bot)
    ctx = _make_ctx()
    # Find 8ball method
    method = None
    for name in ("eight_ball", "eightball", "_8ball", "ball8"):
        if hasattr(cog, name):
            method = getattr(cog, name)
            break
    if method is None:
        # search by command name
        for attr in cog.__dict__.values():
            if hasattr(attr, "name") and "8ball" in str(getattr(attr, "name", "")):
                method = attr
                break
        for cmd in getattr(cog, "__cog_commands__", []):
            if "8ball" in getattr(cmd, "name", ""):
                method = cmd.callback
                break
    assert method is not None, "8ball command not found"
    # call it — should send ephemeral, no DB
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        await method.callback(cog, ctx, question="will it pass?") if hasattr(method, "callback") else await method(
            ctx, question="will it pass?"
        )
    assert ctx.send.await_count >= 1
    kwargs = ctx.send.call_args.kwargs
    assert kwargs.get("ephemeral") is True
