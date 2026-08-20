"""RED tests for RankRenderer — 4.4.

Strict TDD: byte-identical golden bytes to pre-split ImageService.

Strategy: we capture the pre-split output once and compare after split.
This test will FAIL until RankRenderer exists and shares assets.
"""

from __future__ import annotations

import io
from pathlib import Path


def _is_valid_png(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n"


class TestRankRendererGoldenBytes:
    """Rank card output must be byte-identical to pre-split ImageService."""

    def test_rank_renderer_exists_and_returns_valid_png(self) -> None:
        p = Path("bot/services/rank_renderer.py")
        assert p.exists(), "bot/services/rank_renderer.py not found — RED: module missing"
        from bot.services.rank_renderer import RankRenderer

        renderer = RankRenderer()
        buf = renderer.generate_rank_card(
            username="TestUser",
            avatar_url=None,
            xp=500,
            level=3,
            rank=5,
            xp_for_current=300.0,
            xp_for_next=450.0,
        )
        assert isinstance(buf, io.BytesIO)
        assert _is_valid_png(buf.getvalue())

    def test_rank_output_byte_identical_to_image_service(self) -> None:
        """New RankRenderer must produce identical bytes to old ImageService."""
        from bot.services.image_service import ImageService
        from bot.services.rank_renderer import RankRenderer

        kwargs = {
            "username": "TestUser",
            "avatar_url": None,
            "xp": 500,
            "level": 3,
            "rank": 5,
            "xp_for_current": 300.0,
            "xp_for_next": 450.0,
        }
        old = ImageService().generate_rank_card(**kwargs)
        new = RankRenderer().generate_rank_card(**kwargs)
        assert old.getvalue() == new.getvalue(), "Rank card bytes diverged — extraction must be byte-identical"

    def test_rank_renderer_imports_shared_assets(self) -> None:
        src = Path("bot/services/rank_renderer.py").read_text(encoding="utf-8")
        assert "shared_assets" in src, "RankRenderer must import from shared_assets (no duplicated helpers)"
        assert "shared_assets" in src  # from bot.services import shared_assets is valid
        assert "bot.services" in src

    def test_shared_assets_no_cog_view_imports(self) -> None:
        for name in ("greeting_renderer.py", "rank_renderer.py", "shared_assets.py"):
            src = Path(f"bot/services/{name}").read_text(encoding="utf-8")
            assert "bot.cogs" not in src, f"{name} must not import bot.cogs"
            assert "bot.views" not in src, f"{name} must not import bot.views"

    def test_multiple_golden_cases(self) -> None:
        from bot.services.image_service import ImageService
        from bot.services.rank_renderer import RankRenderer

        cases = [
            {"username": "ZeroProgress", "avatar_url": None, "xp": 100, "level": 1, "rank": 10, "xp_for_current": 0.0, "xp_for_next": 150.0},
            {"username": "FullProgress", "avatar_url": None, "xp": 250, "level": 1, "rank": 10, "xp_for_current": 150.0, "xp_for_next": 150.0},
            {
                "username": "SuperLongUsernameThatExceedsTheTypicalDiscordLimit32Chars",
                "avatar_url": None,
                "xp": 300,
                "level": 2,
                "rank": 42,
                "xp_for_current": 50.0,
                "xp_for_next": 225.0,
            },
        ]
        old_svc = ImageService()
        new_svc = RankRenderer()
        for kw in cases:
            assert old_svc.generate_rank_card(**kw).getvalue() == new_svc.generate_rank_card(**kw).getvalue()
