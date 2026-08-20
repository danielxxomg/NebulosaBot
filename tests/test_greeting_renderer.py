"""RED tests for GreetingRenderer — 4.2.

Strict TDD: these tests must FAIL until PillowGreetingRenderer exists
and enforces brand tokens + font fallback.

Scenarios:
- No hex #7289da or GREETING_ACCENT constant in renderer source
- Accent read from bot.utils.brand.ACCENT (not hardcoded)
- Font OSError → ImageFont.load_default() + WARNING
- Protocol exists, no t() calls, render returns PNG
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageFont


def _renderer_source() -> str:
    """Return source of greeting_renderer module as text, or empty if missing."""
    p = Path("bot/services/greeting_renderer.py")
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


class TestGreetingRendererBrandTokens:
    """No hex literals, accent from brand.ACCENT."""

    def test_no_7289da_or_greeting_accent_in_source(self) -> None:
        src = _renderer_source()
        assert src, "bot/services/greeting_renderer.py not found — RED: module missing"
        assert "7289da" not in src.lower(), "stray #7289da hex found — must use brand.ACCENT"
        assert "GREETING_ACCENT" not in src, "GREETING_ACCENT constant must not exist — use brand.ACCENT"

    def test_no_hex_literal_in_greeting_renderer(self) -> None:
        import re

        src = _renderer_source()
        assert src, "bot/services/greeting_renderer.py not found"
        # Purge string literals for brand.py? But brand.py hex is allowed elsewhere.
        # Here we check greeting_renderer only.
        hexes = re.findall(r"#[0-9a-fA-F]{6}", src)
        # Allow hex in comments that reference the old value? No — zero hex.
        assert hexes == [], f"hex literals found in greeting_renderer: {hexes}"

    def test_accent_read_from_brand(self) -> None:
        src = _renderer_source()
        assert src, "bot/services/greeting_renderer.py not found"
        assert "brand.ACCENT" in src or "from bot.utils.brand import" in src or "from bot.utils import brand" in src, (
            "renderer must read accent from bot.utils.brand.ACCENT"
        )
        # Also verify runtime uses brand.ACCENT value, not hardcoded tuple.
        # Import and check that render uses brand.ACCENT-derived RGBA.
        from bot.services.greeting_renderer import PillowGreetingRenderer
        from bot.utils import brand

        # Brand accent as RGBA
        expected = ((brand.ACCENT >> 16) & 255, (brand.ACCENT >> 8) & 255, brand.ACCENT & 255, 255)
        renderer = PillowGreetingRenderer()
        # Render and sample the left accent bar pixel (18, 30) — should be brand accent.
        buf = renderer.render(
            username="User",
            avatar_url=None,
            guild_name="Guild",
            member_count=7,
            card_type="welcome",
            greeting_title="Welcome!",
            member_count_text="Member #7",
            guild_icon_url=None,
        )
        img = Image.open(buf)
        # The left bar is at x=18..24, y=16..(H-16). Sample inside.
        pixel = img.getpixel((20, 30))
        # Allow antialias? Left bar is solid fill rectangle.
        assert pixel[:3] == expected[:3] or pixel == expected, f"accent pixel {pixel} != brand.ACCENT {expected}"

    def test_protocol_exists_and_no_translator(self) -> None:
        from bot.services.greeting_renderer import GreetingRenderer

        assert hasattr(GreetingRenderer, "__protocol_attrs__") or hasattr(GreetingRenderer, "render"), (
            "GreetingRenderer Protocol must define render"
        )
        src = _renderer_source()
        # Renderer must not call t() translator.
        assert "from bot.core.i18n import" not in src and "import t" not in src, (
            "renderer must NOT resolve translations (no t() import)"
        )
        assert "def render" in src or "GreetingRenderer" in src

    def test_render_signature_accepts_translated_strings(self) -> None:
        import inspect

        from bot.services.greeting_renderer import PillowGreetingRenderer

        sig = inspect.signature(PillowGreetingRenderer.render)
        params = sig.parameters
        assert "greeting_title" in params, "render must accept greeting_title"
        assert "member_count_text" in params, "render must accept member_count_text"
        # Should be keyword-only per design.
        for name in (
            "username",
            "avatar_url",
            "guild_name",
            "member_count",
            "card_type",
            "greeting_title",
            "member_count_text",
            "guild_icon_url",
        ):
            assert name in params, f"missing param {name}"


class TestGreetingRendererFontFallback:
    """Font OSError → ImageFont.load_default() + WARNING."""

    def test_font_oserror_falls_back_to_default_and_logs_warning(self, caplog) -> None:
        from bot.services.greeting_renderer import PillowGreetingRenderer

        renderer = PillowGreetingRenderer()
        # Capture a real default font before patching so load_default doesn't
        # call the patched truetype internally.
        dummy_font = ImageFont.load_default()
        # Force font load to raise OSError via shared_assets._load_font path.
        with (
            patch(
                "bot.services.shared_assets.ImageFont.truetype",
                side_effect=OSError("missing font"),
            ),
            patch(
                "bot.services.shared_assets.ImageFont.load_default",
                return_value=dummy_font,
            ) as mock_default,
        ):
            caplog.set_level(logging.WARNING)
            buf = renderer.render(
                username="User",
                avatar_url=None,
                guild_name="Guild",
                member_count=1,
                card_type="welcome",
                greeting_title="Welcome!",
                member_count_text="Member #1",
                guild_icon_url=None,
            )
            # Must have called load_default at least once.
            assert mock_default.called, "OSError must trigger ImageFont.load_default()"
            # Must have logged WARNING.
            warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert any("load_default" in r.getMessage() or "Could not load font" in r.getMessage() for r in warnings), (
                f"expected WARNING about font fallback, got {[r.getMessage() for r in warnings]}"
            )
            assert isinstance(buf, io.BytesIO)
            assert buf.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_missing_avatar_and_guild_icon_use_placeholder(self) -> None:
        from bot.services.greeting_renderer import PillowGreetingRenderer

        renderer = PillowGreetingRenderer()
        buf = renderer.render(
            username="NoAvatar",
            avatar_url=None,
            guild_name="No Icon Guild",
            member_count=1,
            card_type="welcome",
            greeting_title="Welcome!",
            member_count_text="Member #1",
            guild_icon_url=None,
        )
        assert buf.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"
        # Deterministic placeholder — two renders equal.
        buf2 = renderer.render(
            username="NoAvatar",
            avatar_url=None,
            guild_name="No Icon Guild",
            member_count=1,
            card_type="welcome",
            greeting_title="Welcome!",
            member_count_text="Member #1",
            guild_icon_url=None,
        )
        assert buf.getvalue() == buf2.getvalue()

    def test_avatar_fetch_failure_keeps_localized_copy(self) -> None:
        from bot.services.greeting_renderer import PillowGreetingRenderer

        renderer = PillowGreetingRenderer()
        with patch("bot.services.shared_assets._fetch_avatar", side_effect=RuntimeError("network")):
            buf = renderer.render(
                username="Sin Avatar",
                avatar_url="broken-avatar",
                guild_name="Servidor",
                member_count=9,
                card_type="welcome",
                greeting_title="¡Bienvenido!",
                member_count_text="Miembro #9",
                guild_icon_url=None,
            )
        assert buf.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"
