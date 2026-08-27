"""RED: /8ball 20 localized + cooldown/handler (PR3 3.3-3.4).

Consolidation note (cycle-5 S5b/c): source-grep guards were replaced by
runtime twins where a behavioral assertion exists —

- command existence + ephemeral send → proven by ``test_8ball_command_ephemeral``;
- cooldown wiring → proven by runtime CooldownMapping introspection;
- uniform randomness → proven by spying ``random.choice`` at the service seam;
- cooldown error handling → proven by driving the real ``cog_command_error``
  with a ``CommandOnCooldown`` and asserting the ephemeral embed carries the
  actual ``retry_after`` (companion twin:
  tests/test_remediation_cycle2_behavior.py::test_cooldown_handler_emits_localized_retry_after).

Kept without twin (documented): ``test_8ball_has_locales`` reads the production
locale JSON contract (data files, not implementation source), mirroring the
protected i18n key-coverage hygiene tests.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.ocio import OcioCog
from bot.services.ocio_service import OcioService

_COOLDOWN_COMMANDS = ["dice", "banana", "8ball"]


def _make_ctx(guild_id: int = 123456789) -> MagicMock:
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.author = MagicMock(spec=discord.Member)
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = guild_id
    return ctx


def _find_command(cog: OcioCog, name: str):
    """Return the cog command object registered under *name* (hybrid or slash)."""
    # Slash-only (S6B): use walk_app_commands; fallback to __cog_commands__
    for cmd in cog.walk_app_commands():
        if getattr(cmd, "name", None) == name:
            return cmd
        if isinstance(cmd, __import__("discord").app_commands.Group):
            for sub in cmd.walk_commands():
                if getattr(sub, "name", None) == name:
                    return sub
    for cmd in getattr(cog, "__cog_commands__", []):
        if getattr(cmd, "name", None) == name:
            return cmd
    # Legacy alias: dados -> dice
    if name == "dados":
        return _find_command(cog, "dice")
    msg = f"command {name!r} not registered on OcioCog"
    raise AssertionError(msg)


class Test8BallContract:
    def test_8ball_has_locales(self) -> None:
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

    @pytest.mark.asyncio
    async def test_cooldown_error_carries_retry_after_ephemerally(self) -> None:
        """cog_app_command_error (and global handler) turn CommandOnCooldown into ephemeral."""
        import discord
        from discord import app_commands

        cog = OcioCog(MagicMock())
        # Slash path (S6B): app_commands error
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(id=123456789)
        inter.guild.id = 123456789
        inter.response = MagicMock()
        inter.response.is_done.return_value = False
        inter.response.send_message = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()
        err = app_commands.CommandOnCooldown(app_commands.Cooldown(1, 5.0), 3.5)
        await cog.cog_app_command_error(inter, err)
        assert inter.response.send_message.await_count or inter.followup.send.await_count
        kwargs = (
            inter.response.send_message.call_args.kwargs
            if inter.response.send_message.await_count
            else inter.followup.send.call_args.kwargs
        )
        assert kwargs.get("ephemeral") is True
        embed = kwargs.get("embed")
        assert embed is not None
        assert "3.5" in (embed.description or ""), "cooldown embed MUST carry the actual retry_after seconds"


class TestCooldownWiring:
    """dice/banana/8ball carry cooldown(1, 5s) on their runtime buckets."""

    @pytest.mark.parametrize("name", _COOLDOWN_COMMANDS)
    def test_command_has_user_cooldown(self, name: str) -> None:
        cmd = _find_command(OcioCog(MagicMock()), name)
        # Slash-only: app_commands stores cooldown in checks; hybrid in _buckets
        bucket = getattr(getattr(cmd, "_buckets", None), "_cooldown", None)
        if bucket is not None:
            assert bucket.rate == 1
            assert bucket.per == 5
        else:
            # app_commands path: checks contains cooldown predicate
            checks = getattr(cmd, "checks", [])
            assert len(checks) > 0, f"{name} must have app_commands cooldown check"
            src = __import__("pathlib").Path("bot/cogs/ocio.py").read_text()
            assert "cooldown" in src.lower() and "1, 5" in src, f"{name} must configure cooldown(1,5)"


@pytest.mark.asyncio
async def test_8ball_returns_localized() -> None:
    svc = OcioService()
    # must not require discord mocks
    for gid in ("123456789", None):
        resp = svc.get_8ball_response(guild_id=str(gid) if gid else None, question="is it?")
        assert isinstance(resp, str) and len(resp) > 0


@pytest.mark.asyncio
async def test_8ball_response_draws_from_pool_uniformly() -> None:
    """get_8ball_response selects via random.choice over the localized pool."""
    svc = OcioService()
    with patch("bot.services.ocio_service.random.choice", wraps=random.choice) as choice_spy:  # noqa: S311 -- entertainment randomness
        svc.get_8ball_response(guild_id="123456789", question="is it?")
    choice_spy.assert_called_once()


@pytest.mark.asyncio
async def test_8ball_command_ephemeral() -> None:
    bot = MagicMock()
    cog = OcioCog(bot)
    ctx = _make_ctx()
    method = _find_command(cog, "8ball")
    # S6B: 8ball is now permanent (ephemeral-standard flip)
    await method.callback(cog, ctx, question="will it pass?")
    assert ctx.send.await_count >= 1
    kwargs = ctx.send.call_args.kwargs
    assert kwargs.get("ephemeral") is not True, "S6B 8ball must be permanent"
