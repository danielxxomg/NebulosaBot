"""RankRenderer behavioral coverage.

Renderer must produce a valid PNG through the shared-assets pipeline and
respect services-layer import boundaries. (The former byte-identity golden
tests compared against the deleted ImageService shim and were removed with
it in cycle-5 S5a.)
"""

from __future__ import annotations

import io
from pathlib import Path

from bot.services.rank_renderer import RankRenderer


def _is_valid_png(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n"


class TestRankRendererBehavior:
    """Rank card renderer produces valid output via shared assets."""

    def test_rank_renderer_exists_and_returns_valid_png(self) -> None:
        p = Path("bot/services/rank_renderer.py")
        assert p.exists(), "bot/services/rank_renderer.py not found — RED: module missing"

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

    def test_rank_renderer_imports_shared_assets(self) -> None:
        src = Path("bot/services/rank_renderer.py").read_text(encoding="utf-8")
        assert "from bot.services import shared_assets" in src, (
            "RankRenderer must import from shared_assets (no duplicated helpers)"
        )
        assert "bot.services" in src

    def test_shared_assets_no_cog_view_imports(self) -> None:
        for name in ("greeting_renderer.py", "rank_renderer.py", "shared_assets.py"):
            src = Path(f"bot/services/{name}").read_text(encoding="utf-8")
            assert "bot.cogs" not in src, f"{name} must not import bot.cogs"
            assert "bot.views" not in src, f"{name} must not import bot.views"
