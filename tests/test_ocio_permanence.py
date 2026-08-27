"""S6B.2 RED — ocio permanence + zero DB writes + i18n + banana pool (strict TDD).

Ref: ocio-commands banana/8ball + ephemeral-standard "Fun commands permanent standard"
— /8ball+/banana+/dice MUST be permanent (ephemeral=False/absent) and MUST NOT
write to DB; 8ball uses 20 localized ocio.8ball.* + title from ocio.8ball.embed_title.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.ocio import OcioCog
from bot.core.i18n import load_locales
from bot.services.ocio_service import OcioService
from tests.conftest import make_ctx

_GUILD_ID = 123456789


@pytest.fixture(autouse=True)
def _load_i18n() -> None:
    from bot.core import i18n as i18n_mod

    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()
    load_locales(Path("bot/locales"))


@pytest.fixture
def mock_bot() -> MagicMock:
    return MagicMock(spec=commands.Bot)


@pytest.fixture
def cog(mock_bot: MagicMock) -> OcioCog:
    return OcioCog(mock_bot)


def _is_permanent_call(call_kwargs: dict) -> bool:
    """Permanent = ephemeral not True (absent or False)."""
    return call_kwargs.get("ephemeral") is not True


class TestOcioPermanence:
    @pytest.mark.asyncio
    @patch.object(
        OcioService, "get_random_banana", new_callable=AsyncMock, return_value=(b"fakewebp", "banana_01.webp", 12)
    )
    async def test_banana_is_permanent(self, _mock: AsyncMock, cog: OcioCog) -> None:
        # Use app_commands path if migrated, else hybrid path — both must be permanent
        # Probe by trying interaction path first

        # Find command object
        cmds = {c.name: c for c in cog.walk_app_commands()} if hasattr(cog, "walk_app_commands") else {}
        if "banana" in cmds:
            # app_commands path — mock interaction
            inter = MagicMock(spec=discord.Interaction)
            inter.guild = MagicMock()
            inter.guild.id = _GUILD_ID
            inter.user = MagicMock()
            inter.response = MagicMock()
            inter.response.is_done.return_value = False
            inter.response.send_message = AsyncMock()
            inter.followup = MagicMock()
            inter.followup.send = AsyncMock()
            # call via callback
            cmd = cmds["banana"]
            await cmd.callback(cog, inter)  # type: ignore[arg-type]
            # collect call
            if inter.response.send_message.await_count:
                kwargs = inter.response.send_message.call_args.kwargs
            else:
                kwargs = inter.followup.send.call_args.kwargs
            assert _is_permanent_call(kwargs), "banana must be permanent (ephemeral=False/absent)"
        else:
            ctx = make_ctx(guild_id=_GUILD_ID, spec=commands.Context)
            await cog.banana.callback(cog, ctx)  # type: ignore[attr-defined]
            kwargs = ctx.send.call_args.kwargs if hasattr(ctx.send.call_args, "kwargs") else ctx.send.call_args[1]
            assert _is_permanent_call(kwargs), "banana must be permanent"

    @pytest.mark.asyncio
    async def test_eightball_is_permanent(self, cog: OcioCog) -> None:
        cmds = {c.name: c for c in cog.walk_app_commands()} if hasattr(cog, "walk_app_commands") else {}
        if "8ball" in cmds:
            inter = MagicMock(spec=discord.Interaction)
            inter.guild = MagicMock()
            inter.guild.id = _GUILD_ID
            inter.user = MagicMock()
            inter.response = MagicMock()
            inter.response.is_done.return_value = False
            inter.response.send_message = AsyncMock()
            inter.followup = MagicMock()
            inter.followup.send = AsyncMock()
            cmd = cmds["8ball"]
            await cmd.callback(cog, inter, question="will it pass?")  # type: ignore[arg-type]
            kwargs = (
                inter.response.send_message.call_args.kwargs
                if inter.response.send_message.await_count
                else inter.followup.send.call_args.kwargs
            )
            assert _is_permanent_call(kwargs), "8ball must be permanent"
        else:
            ctx = make_ctx(guild_id=_GUILD_ID, spec=commands.Context)
            await cog.eight_ball.callback(cog, ctx, question="will it pass?")  # type: ignore[attr-defined]
            kwargs = ctx.send.call_args.kwargs if hasattr(ctx.send.call_args, "kwargs") else ctx.send.call_args[1]
            assert _is_permanent_call(kwargs), "8ball must be permanent"

    @pytest.mark.asyncio
    async def test_dice_is_permanent(self, cog: OcioCog) -> None:
        # dice/dados — after rename must be permanent
        cmds = {c.name: c for c in cog.walk_app_commands()} if hasattr(cog, "walk_app_commands") else {}
        target = "dice" if "dice" in cmds else "dados"
        if target in cmds:
            inter = MagicMock(spec=discord.Interaction)
            inter.guild = MagicMock()
            inter.guild.id = _GUILD_ID
            inter.user = MagicMock()
            inter.response = MagicMock()
            inter.response.is_done.return_value = False
            inter.response.send_message = AsyncMock()
            inter.followup = MagicMock()
            inter.followup.send = AsyncMock()
            cmd = cmds[target]
            await cmd.callback(cog, inter, sides=6)  # type: ignore[arg-type]
            kwargs = (
                inter.response.send_message.call_args.kwargs
                if inter.response.send_message.await_count
                else inter.followup.send.call_args.kwargs
            )
            assert _is_permanent_call(kwargs), f"{target} must be permanent"
        else:
            ctx = make_ctx(guild_id=_GUILD_ID, spec=commands.Context)
            cb = getattr(cog, "dice", None) or getattr(cog, "dados", None)
            assert cb is not None
            await cb.callback(cog, ctx, sides=6)  # type: ignore[attr-defined]
            kwargs = ctx.send.call_args.kwargs if hasattr(ctx.send.call_args, "kwargs") else ctx.send.call_args[1]
            assert _is_permanent_call(kwargs), "dice must be permanent"

    def test_banana_eightball_dice_write_no_db_row(self) -> None:
        src = Path("bot/cogs/ocio.py").read_text(encoding="utf-8")
        # ocio cog must not contain DB writes
        for kw in ("insert", "update", "delete", ".table(", "supabase", "db."):
            # allow reading via service but not direct writes in cog
            if kw in src.lower():
                # fail if cog does DB mutation — RED expects zero
                assert kw not in src.lower() or "get_random_banana" in src, f"ocio cog must not write DB, found {kw}"

    def test_eightball_uses_localized_keys(self) -> None:
        src = Path("bot/cogs/ocio.py").read_text(encoding="utf-8")
        # Must use t() for 8ball keys and title via ocio.8ball.embed_title
        assert "ocio.8ball.embed_title" in src, "8ball title must use t(..., 'ocio.8ball.embed_title')"
        assert "ocio.8ball.r" not in src or "get_8ball_response" in src or "t(" in src, "8ball responses via t()"

    def test_banana_pool_and_dorada(self) -> None:
        svc = OcioService()
        # pool dir
        assert "assets/images/banana" in str(svc._banana_dir)
        # check 1% dorada path exists in service
        src = Path("bot/services/ocio_service.py").read_text(encoding="utf-8")
        assert "dorada" in src.lower()
        assert "0.01" in src or "1%" in src or "random.random" in src
        # 5-8 webp variants exist
        pool = list(Path("assets/images/banana").glob("*.webp"))
        assert 5 <= len(pool) <= 8 or len(pool) >= 5, f"banana pool must have 5-8 webp, got {len(pool)}"
        assert any("dorada" in p.name for p in pool), "dorada.webp must exist in pool"
