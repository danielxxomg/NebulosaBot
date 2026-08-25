# ruff: noqa: S108,RUF015,RUF002,RUF003,S311
"""RED: OcioService.get_random_banana - Strict TDD (PR3 3.1).

Covers:
- pool assets/images/banana/*.webp 5-8 incl dorada.webp, 1 pct dorada 30cm weighted,
  empty to Pillow placeholder, missing/corrupt to Pillow via asyncio.to_thread,
  no Discord imports.
Strict TDD: MUST FAIL before GREEN.
"""

from __future__ import annotations

import asyncio
import operator
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.services import ocio_service as ocio_service_mod
from bot.services.ocio_service import OcioService


class TestOcioServiceExists:
    def test_module_exists(self) -> None:
        assert hasattr(ocio_service_mod, "OcioService")

    def test_no_discord_import(self) -> None:
        # Structural guard retained (cycle-5 S5b/c audit): a behavioral
        # import-probe twin is impossible — bot.core.i18n legitimately imports
        # discord, so blocking discord at the import gate false-positives on
        # any service importing t(). Direct-import discipline can only be
        # asserted against the module's own source text.
        src = Path(ocio_service_mod.__file__).read_text(encoding="utf-8")
        assert "import discord" not in src and "from discord" not in src, "OcioService MUST NOT import discord"


class TestGetRandomBanana:
    @pytest.mark.asyncio
    async def test_normal_pool_pick(self) -> None:
        svc = OcioService(banana_dir=Path("assets/images/banana"))
        with (
            patch("bot.services.ocio_service.random.random", return_value=0.5),
            patch("bot.services.ocio_service.random.choice", side_effect=operator.itemgetter(0)),
            patch("bot.services.ocio_service.random.randint", return_value=12),
        ):
            data, filename, cm = await svc.get_random_banana()
            assert isinstance(data, (bytes, bytearray))
            assert len(data) > 0
            assert filename.endswith(".webp")
            assert 2 <= cm <= 30

    @pytest.mark.asyncio
    async def test_dorada_1pct_30cm(self) -> None:
        svc = OcioService(banana_dir=Path("assets/images/banana"))
        with patch("bot.services.ocio_service.random.random", return_value=0.005):
            data, filename, cm = await svc.get_random_banana()
            assert "dorada" in filename.lower()
            assert cm == 30
            assert len(data) > 0

    @pytest.mark.asyncio
    async def test_empty_pool_fallback(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty-banana"
        empty.mkdir()
        svc = OcioService(banana_dir=empty)
        data, filename, cm = await svc.get_random_banana()
        assert len(data) > 0
        assert filename.endswith(".webp")
        assert 2 <= cm <= 30

    @pytest.mark.asyncio
    async def test_missing_corrupt_fallback_returns_bytes(self) -> None:
        svc = OcioService(banana_dir=Path("assets/images/banana"))
        fake_path = Path("/tmp/fake_missing_banana_xyz.webp")
        with (
            patch.object(Path, "glob", return_value=[fake_path]),
            patch("bot.services.ocio_service.random.random", return_value=0.5),
            patch("bot.services.ocio_service.random.choice", side_effect=operator.itemgetter(0)),
        ):
            data, _filename, _cm = await svc.get_random_banana()
            assert len(data) > 0

    @pytest.mark.asyncio
    async def test_placeholder_render_runs_via_to_thread(self, tmp_path: Path) -> None:
        """Empty pool → Pillow placeholder rendered off-loop via asyncio.to_thread.

        Consolidation note (cycle-5 S5b/c): replaces two source greps (read_text
        + inspect.getsource for 'to_thread') with a spying wrapper around the
        real asyncio.to_thread on the actual fallback execution path.
        """
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

    def test_pool_size_5_to_8(self) -> None:
        pool = list(Path("assets/images/banana").glob("*.webp"))
        assert 5 <= len(pool) <= 8, f"pool size {len(pool)} must be 5-8"
        names = [p.name for p in pool]
        assert "dorada.webp" in names
