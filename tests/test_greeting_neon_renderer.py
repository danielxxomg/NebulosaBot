"""RED tests for neon greeting theme rendering (PR1 task 3.1).

Asserts ``PillowGreetingRenderer.render(theme_id="gaming_neon")`` returns
valid PNG bytes for welcome + goodbye, that the renderer source contains
no neon hex literals (tokens come from ``brand``), and that unknown /
``None`` theme_id falls back to the default render.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image

from bot.services.greeting_renderer import PillowGreetingRenderer
from bot.utils import brand

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

_RENDERER_PATH = Path("bot/services/greeting_renderer.py")


def _renderer_source() -> str:
    return _RENDERER_PATH.read_text(encoding="utf-8")


def _render_neon(card_type: str) -> bytes:
    renderer = PillowGreetingRenderer()
    buf = renderer.render(
        username="NeonUser",
        avatar_url=None,
        guild_name="Neon Guild",
        member_count=7,
        card_type=card_type,
        greeting_title="Welcome!" if card_type == "welcome" else "Goodbye!",
        member_count_text="Member #7",
        guild_icon_url=None,
        theme_id="gaming_neon",
    )
    return buf.getvalue()


class TestNeonRenderProducesPng:
    """3.1 — gaming_neon renders valid PNG for welcome + goodbye."""

    def test_neon_welcome_returns_png_magic_bytes(self) -> None:
        data = _render_neon("welcome")
        assert data[:8] == PNG_MAGIC

    def test_neon_goodbye_returns_png_magic_bytes(self) -> None:
        data = _render_neon("goodbye")
        assert data[:8] == PNG_MAGIC

    def test_neon_render_is_loadable_image(self) -> None:
        data = _render_neon("welcome")
        img = Image.open(io.BytesIO(data))
        assert img.size == (934, 282)
        assert img.mode == "RGBA"


class TestNeonNoHexLiterals:
    """3.1 — renderer source must not hardcode the neon hex values."""

    def test_no_neon_hex_in_renderer_source(self) -> None:
        src = _renderer_source()
        assert re.search(r"#FF2E97", src, re.IGNORECASE) is None
        assert re.search(r"#00E5FF", src, re.IGNORECASE) is None

    def test_neon_colors_read_from_brand(self) -> None:
        src = _renderer_source()
        assert "brand.ACCENT_A" in src
        assert "brand.ACCENT_B" in src


class TestNeonThemeFallback:
    """3.1 — unknown / None theme_id falls back to default render."""

    def test_unknown_theme_falls_back_to_default(self) -> None:
        renderer = PillowGreetingRenderer()
        common = {
            "username": "User",
            "avatar_url": None,
            "guild_name": "Guild",
            "member_count": 1,
            "card_type": "welcome",
            "greeting_title": "Welcome!",
            "member_count_text": "Member #1",
            "guild_icon_url": None,
        }
        default_buf = renderer.render(**common)
        unknown_buf = renderer.render(theme_id="does_not_exist", **common)
        # Unknown theme must equal default render (fallback), not crash.
        assert default_buf.getvalue() == unknown_buf.getvalue()

    def test_none_theme_matches_default(self) -> None:
        renderer = PillowGreetingRenderer()
        common = {
            "username": "User",
            "avatar_url": None,
            "guild_name": "Guild",
            "member_count": 1,
            "card_type": "welcome",
            "greeting_title": "Welcome!",
            "member_count_text": "Member #1",
            "guild_icon_url": None,
        }
        explicit_none = renderer.render(theme_id=None, **common)
        default_buf = renderer.render(**common)
        assert explicit_none.getvalue() == default_buf.getvalue()

    def test_neon_render_differs_from_default(self) -> None:
        """Neon overlay must actually change the rendered bytes."""
        renderer = PillowGreetingRenderer()
        common = {
            "username": "User",
            "avatar_url": None,
            "guild_name": "Guild",
            "member_count": 1,
            "card_type": "welcome",
            "greeting_title": "Welcome!",
            "member_count_text": "Member #1",
            "guild_icon_url": None,
        }
        default_buf = renderer.render(**common)
        neon_buf = renderer.render(theme_id="gaming_neon", **common)
        assert default_buf.getvalue() != neon_buf.getvalue(), (
            "gaming_neon render must differ from default (overlay not applied)"
        )


class TestNeonUsesBrandPalette:
    """The neon overlay must actually paint the ACCENT_A/B colors into pixels."""

    def test_neon_render_contains_accent_a_pixels(self) -> None:
        data = _render_neon("welcome")
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        a_rgb = ((brand.ACCENT_A >> 16) & 255, (brand.ACCENT_A >> 8) & 255, brand.ACCENT_A & 255)
        b_rgb = ((brand.ACCENT_B >> 16) & 255, (brand.ACCENT_B >> 8) & 255, brand.ACCENT_B & 255)
        pix = img.load()
        w, h = img.size
        found_a = found_b = False
        for y in range(h):
            for x in range(w):
                p = pix[x, y]
                if p[:3] == a_rgb:
                    found_a = True
                if p[:3] == b_rgb:
                    found_b = True
                if found_a and found_b:
                    break
            if found_a and found_b:
                break
        assert found_a, "no ACCENT_A (magenta) pixel found in neon render"
        assert found_b, "no ACCENT_B (cyan) pixel found in neon render"
