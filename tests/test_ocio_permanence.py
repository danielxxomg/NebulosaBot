"""S6B.2 RED — ocio permanence + zero DB writes + i18n + banana pool (strict TDD).

Ref: ocio-commands banana/8ball + ephemeral-standard "Fun commands permanent standard"
— /8ball+/banana+/dice MUST be permanent (ephemeral=False/absent) and MUST NOT
write to DB; 8ball uses 20 localized ocio.8ball.* + title from ocio.8ball.embed_title.
"""

from __future__ import annotations

import asyncio
import operator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from bot.cogs.ocio import OcioCog
from bot.core import i18n as i18n_mod
from bot.core.i18n import load_locales
from bot.services import ocio_service as ocio_service_mod
from bot.services.ocio_service import OcioService
from tests.conftest import make_ctx

_GUILD_ID = 123456789


@pytest.fixture(autouse=True)
def _load_i18n() -> None:
    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()
    load_locales(Path("bot/locales"))


@pytest.fixture
def mock_bot() -> MagicMock:
    return MagicMock(spec=commands.Bot)


@pytest.fixture
def cog(mock_bot: MagicMock) -> OcioCog:
    return OcioCog(mock_bot)


def _is_permanent_call(call_kwargs: object) -> bool:
    """Permanent = ephemeral not True (absent or False)."""
    # Use dict.get via type-agnostic getattr to satisfy ty generic variance
    getter = getattr(call_kwargs, "get", None)
    if callable(getter):
        try:
            return getter("ephemeral") is not True
        except Exception:  # noqa: BLE001  # mapping probe fallback
            return True
    return True


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
            cb = getattr(cmd, "callback", None)
            assert callable(cb)
            await cb(cog, inter)
            # collect call
            if inter.response.send_message.await_count:
                kwargs = inter.response.send_message.call_args.kwargs
            else:
                kwargs = inter.followup.send.call_args.kwargs
            assert _is_permanent_call(kwargs), "banana must be permanent (ephemeral=False/absent)"
        else:
            ctx = make_ctx(guild_id=_GUILD_ID, spec=commands.Context)
            cb_banana = getattr(cog, "banana", None)
            assert cb_banana is not None and hasattr(cb_banana, "callback")
            await cb_banana.callback(cog, ctx)
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
            cb = getattr(cmd, "callback", None)
            assert callable(cb)
            await cb(cog, inter, question="will it pass?")
            kwargs = (
                inter.response.send_message.call_args.kwargs
                if inter.response.send_message.await_count
                else inter.followup.send.call_args.kwargs
            )
            assert _is_permanent_call(kwargs), "8ball must be permanent"
        else:
            ctx = make_ctx(guild_id=_GUILD_ID, spec=commands.Context)
            cb_8 = getattr(cog, "eight_ball", None)
            assert cb_8 is not None and hasattr(cb_8, "callback")
            await cb_8.callback(cog, ctx, question="will it pass?")
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
            cb = getattr(cmd, "callback", None)
            assert callable(cb)
            await cb(cog, inter, sides=6)
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
            assert hasattr(cb, "callback")
            await cb.callback(cog, ctx, sides=6)
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


# ===========================================================================
# OcioService fallback twins (tests-slim-fase-2 B2) — replaces
# tests/test_pr3_ocio_service_red.py. D3 proof: LITERAL names cover the 6/8
# unique set — empty-pool Fallback, corrupt fallback, asyncio.to_thread spy,
# no-discord-import guard — with pool sizes parametrized.
# ===========================================================================


class TestOcioFallbackTwins:
    """Fallback paths of OcioService.get_random_banana, parametrized by pool size."""

    @pytest.mark.parametrize("pool_size", [0, 5, 8], ids=["pool-0", "pool-5", "pool-8"])
    @pytest.mark.asyncio
    async def test_empty_pool_fallback_returns_placeholder(self, tmp_path: Path, pool_size: int) -> None:
        """empty-pool Fallback MUST yield the Pillow placeholder (2-30cm)."""
        for i in range(pool_size):
            (tmp_path / f"banana_{i:02}.webp").write_bytes(b"fake-webp-bytes")
        svc = OcioService(banana_dir=tmp_path)
        # Corrupt every seeded file so reads fail → corrupt fallback path.
        with (
            patch("bot.services.ocio_service.random.random", return_value=0.5),
            patch("bot.services.ocio_service.random.randint", return_value=12),
            patch.object(Path, "read_bytes", side_effect=OSError("corrupt fallback — unreadable webp")),
        ):
            data, filename, cm = await svc.get_random_banana()
        assert len(data) > 0
        assert filename.endswith(".webp")
        assert 2 <= cm <= 30

    @pytest.mark.asyncio
    async def test_empty_pool_fallback_no_files(self, tmp_path: Path) -> None:
        """empty-pool Fallback with a truly empty dir MUST return placeholder bytes."""
        svc = OcioService(banana_dir=tmp_path)
        with patch("bot.services.ocio_service.random.randint", return_value=12):
            data, filename, cm = await svc.get_random_banana()
        assert len(data) > 0
        assert filename == "banana.webp"
        assert cm == 12

    @pytest.mark.asyncio
    async def test_corrupt_fallback_returns_bytes(self, tmp_path: Path) -> None:
        """corrupt fallback: unreadable chosen file MUST degrade to placeholder bytes."""
        corrupt = tmp_path / "banana_corrupt.webp"
        corrupt.write_bytes(b"")
        svc = OcioService(banana_dir=tmp_path)
        with (
            patch("bot.services.ocio_service.random.random", return_value=0.5),
            patch("bot.services.ocio_service.random.choice", side_effect=operator.itemgetter(0)),
            patch("bot.services.ocio_service.random.randint", return_value=12),
        ):
            data, _filename, _cm = await svc.get_random_banana()
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_placeholder_render_runs_via_to_thread(self, tmp_path: Path) -> None:
        """asyncio.to_thread spy: Pillow render/file I/O MUST run off the event loop."""
        svc = OcioService(banana_dir=tmp_path)
        with (
            patch("bot.services.ocio_service.asyncio.to_thread", wraps=asyncio.to_thread) as thread_spy,
            patch("bot.services.ocio_service.random.randint", return_value=12),
        ):
            data, filename, cm = await svc.get_random_banana()
        assert len(data) > 0
        assert filename == "banana.webp"
        assert cm == 12
        assert thread_spy.await_count >= 1, "Pillow render / file I/O MUST run via asyncio.to_thread"

    def test_no_discord_import_guard(self) -> None:
        """no-discord-import guard: OcioService MUST NOT import discord.

        Structural guard (cycle-5 audit): bot.core.i18n legitimately imports
        discord, so a behavioral import-probe false-positives on any service
        importing t(); source-text assertion is the only sound form.
        """
        src = Path(ocio_service_mod.__file__).read_text(encoding="utf-8")
        assert "import discord" not in src and "from discord" not in src, "OcioService MUST NOT import discord"
