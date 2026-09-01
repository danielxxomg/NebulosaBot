"""S1 RED: greeting template registry — 4 keys, unknown→default, t()-free, no hex, byte-identity."""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import TypedDict

from PIL import Image

from bot.utils import brand

RENDERER_PATH = Path("bot/services/greeting_renderer.py")


class _RenderKwargs(TypedDict):
    username: str
    avatar_url: str | None
    guild_name: str
    member_count: int
    card_type: str
    greeting_title: str
    member_count_text: str
    guild_icon_url: str | None


def _renderer_source() -> str:
    return RENDERER_PATH.read_text(encoding="utf-8")


class TestRegistryFourTemplates:
    def test_registry_enumerates_exactly_four_keys(self) -> None:
        from bot.services.greeting_renderer import TEMPLATE_REGISTRY

        assert set(TEMPLATE_REGISTRY.keys()) == {
            "default",
            "gaming_neon",
            "sunset_wave",
            "minimal_light",
        }

    def test_template_dataclass_has_required_attrs(self) -> None:
        from bot.services.greeting_renderer import TEMPLATE_REGISTRY, Template

        for key, tmpl in TEMPLATE_REGISTRY.items():
            assert isinstance(tmpl, Template)
            assert tmpl.id == key
            assert isinstance(tmpl.label_key, str) and tmpl.label_key
            assert isinstance(tmpl.description_key, str) and tmpl.description_key
            # overlay_fn is callable or None
            assert tmpl.overlay_fn is None or callable(tmpl.overlay_fn)

    def test_gaming_neon_overlay_is_neon(self) -> None:
        from bot.services.greeting_renderer import TEMPLATE_REGISTRY, _render_neon_overlay

        assert TEMPLATE_REGISTRY["gaming_neon"].overlay_fn is _render_neon_overlay

    def test_default_has_no_overlay(self) -> None:
        from bot.services.greeting_renderer import TEMPLATE_REGISTRY

        assert TEMPLATE_REGISTRY["default"].overlay_fn is None


class TestUnknownFallback:
    def test_unknown_template_id_renders_default_bytes(self) -> None:
        from bot.services.greeting_renderer import PillowGreetingRenderer

        r = PillowGreetingRenderer()
        common: _RenderKwargs = {
            "username": "User",
            "avatar_url": None,
            "guild_name": "Guild",
            "member_count": 1,
            "card_type": "welcome",
            "greeting_title": "Welcome!",
            "member_count_text": "Member #1",
            "guild_icon_url": None,
        }
        default_buf = r.render(template_id="default", **common).getvalue()
        unknown_buf = r.render(template_id="unknown_xyz", **common).getvalue()
        assert unknown_buf == default_buf

    def test_none_renders_default(self) -> None:
        from bot.services.greeting_renderer import PillowGreetingRenderer

        r = PillowGreetingRenderer()
        common: _RenderKwargs = {
            "username": "User",
            "avatar_url": None,
            "guild_name": "Guild",
            "member_count": 1,
            "card_type": "welcome",
            "greeting_title": "Welcome!",
            "member_count_text": "Member #1",
            "guild_icon_url": None,
        }
        a = r.render(template_id=None, **common).getvalue()
        b = r.render(**common).getvalue()
        assert a == b
        # also template_id None explicitly equals default
        c = r.render(template_id="default", **common).getvalue()
        assert a == c

    def test_theme_id_alias_fallback(self) -> None:
        from bot.services.greeting_renderer import PillowGreetingRenderer

        r = PillowGreetingRenderer()
        common: _RenderKwargs = {
            "username": "User",
            "avatar_url": None,
            "guild_name": "Guild",
            "member_count": 1,
            "card_type": "welcome",
            "greeting_title": "Welcome!",
            "member_count_text": "Member #1",
            "guild_icon_url": None,
        }
        # theme_id alias must also fallback to default for unknown
        unknown_via_theme = r.render(theme_id="unknown_xyz", **common).getvalue()
        default = r.render(template_id="default", **common).getvalue()
        assert unknown_via_theme == default


class TestRendererTFree:
    def test_renderer_never_imports_or_calls_t(self) -> None:
        src = _renderer_source()
        assert "from bot.core.i18n import" not in src
        assert "import t" not in src
        # Docstring mentions t() but code must not call it — check no real call site
        # Real call pattern is t( with a quoted key like t(" or t(' or t(guild
        assert re.search(r"\bt\(.*greeting", src) is None
        assert "from bot.core.i18n" not in src

    def test_renderer_does_not_import_cogs_or_views(self) -> None:
        src = _renderer_source()
        assert "from bot.cogs" not in src
        assert "from bot.views" not in src


class TestRendererNoHex:
    def test_no_hex_literals_in_renderer(self) -> None:
        src = _renderer_source()
        hexes = re.findall(r"#[0-9a-fA-F]{6}", src)
        assert hexes == [], f"hex literals found in greeting_renderer: {hexes}"

    def test_no_orphan_hex_outside_brand(self) -> None:
        # Ensure brand tokens are used, not hardcoded via 0x... either? The spec
        # allows brand token usage; check renderer does not contain raw hex int for neon.
        src = _renderer_source()
        assert "0xFF2E97" not in src
        assert "0x00E5FF" not in src
        assert "0xA855F7" not in src or "brand.ACCENT" in src  # if hex appears, must be via brand


class TestGamingNeonByteIdentity:
    def test_gaming_neon_overlay_applied_portable(self) -> None:
        """Neon overlay must actually paint ACCENT_A/B pixels (portable across Pillow versions).

        The one-time pre/post-refactor byte-identity was proven at apply time in a
        single environment (sha256 c59de301…, recorded in the SDD evidence);
        cross-environment PNG hashes are NOT stable across Pillow versions
        (CI pillow 12.3.0 encodes differently), so this regression test asserts
        the overlay contract via pixel scanning instead of a frozen hash.
        """
        from bot.services.greeting_renderer import PillowGreetingRenderer

        r = PillowGreetingRenderer()
        neon = r.render(
            username="TestUser",
            avatar_url=None,
            guild_name="TestGuild",
            member_count=42,
            card_type="welcome",
            greeting_title="Welcome",
            member_count_text="Member #42",
            template_id="gaming_neon",
        )
        default = r.render(
            username="TestUser",
            avatar_url=None,
            guild_name="TestGuild",
            member_count=42,
            card_type="welcome",
            greeting_title="Welcome",
            member_count_text="Member #42",
            template_id="default",
        )
        assert neon.getvalue() != default.getvalue(), "neon overlay not applied"

        img = Image.open(io.BytesIO(neon.getvalue())).convert("RGBA")
        a_rgb = ((brand.ACCENT_A >> 16) & 255, (brand.ACCENT_A >> 8) & 255, brand.ACCENT_A & 255)
        b_rgb = ((brand.ACCENT_B >> 16) & 255, (brand.ACCENT_B >> 8) & 255, brand.ACCENT_B & 255)
        pix = img.load()
        assert pix is not None, "load() must return a PixelAccess for a valid image"
        w, h = img.size
        found_a = found_b = False
        for y in range(h):
            for x in range(w):
                p = pix[x, y]
                if not isinstance(p, tuple):
                    continue
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

    def test_gaming_neon_via_theme_id_matches_template_id(self) -> None:
        from bot.services.greeting_renderer import PillowGreetingRenderer

        r = PillowGreetingRenderer()
        a = r.render(
            username="TestUser",
            avatar_url=None,
            guild_name="TestGuild",
            member_count=42,
            card_type="welcome",
            greeting_title="Welcome",
            member_count_text="Member #42",
            template_id="gaming_neon",
        ).getvalue()
        b = r.render(
            username="TestUser",
            avatar_url=None,
            guild_name="TestGuild",
            member_count=42,
            card_type="welcome",
            greeting_title="Welcome",
            member_count_text="Member #42",
            theme_id="gaming_neon",
        ).getvalue()
        assert a == b

    def test_gaming_neon_differs_from_default(self) -> None:
        from bot.services.greeting_renderer import PillowGreetingRenderer

        r = PillowGreetingRenderer()
        common: _RenderKwargs = {
            "username": "User",
            "avatar_url": None,
            "guild_name": "Guild",
            "member_count": 1,
            "card_type": "welcome",
            "greeting_title": "Welcome!",
            "member_count_text": "Member #1",
            "guild_icon_url": None,
        }
        default = r.render(template_id="default", **common).getvalue()
        neon = r.render(template_id="gaming_neon", **common).getvalue()
        assert default != neon

    def test_neon_overlay_uses_gaussian_blur_8(self) -> None:
        src = _renderer_source()
        assert "GaussianBlur" in src
        assert re.search(r"GaussianBlur\s*\(\s*radius\s*=\s*8\s*\)", src) is not None

    def test_neon_uses_brand_accent_a_b(self) -> None:
        src = _renderer_source()
        assert "brand.ACCENT_A" in src
        assert "brand.ACCENT_B" in src


class TestDualParamRender:
    def test_render_accepts_both_template_and_theme(self) -> None:
        import inspect

        from bot.services.greeting_renderer import PillowGreetingRenderer

        sig = inspect.signature(PillowGreetingRenderer.render)
        assert "template_id" in sig.parameters
        assert "theme_id" in sig.parameters

    def test_sunset_and_minimal_render_png(self) -> None:
        from bot.services.greeting_renderer import PillowGreetingRenderer

        r = PillowGreetingRenderer()
        for tid in ("sunset_wave", "minimal_light"):
            buf = r.render(
                username="User",
                avatar_url=None,
                guild_name="Guild",
                member_count=1,
                card_type="welcome",
                greeting_title="Welcome!",
                member_count_text="Member #1",
                template_id=tid,
            )
            data = buf.getvalue()
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
            img = Image.open(io.BytesIO(data))
            assert img.size == (934, 282)
            assert img.mode == "RGBA"

    def test_sunset_minimal_use_brand_tokens_only(self) -> None:
        src = _renderer_source()
        # Ensure overlays reference brand tokens, not hex
        assert "brand.WARNING" in src or "brand.ERROR" in src or "brand.PANEL_OVERLAY" in src
        assert "brand.ACCENT" in src

    def test_sunset_minimal_via_theme_id_alias(self) -> None:
        from bot.services.greeting_renderer import PillowGreetingRenderer

        r = PillowGreetingRenderer()
        for tid in ("sunset_wave", "minimal_light"):
            a = r.render(
                username="User",
                avatar_url=None,
                guild_name="Guild",
                member_count=1,
                card_type="welcome",
                greeting_title="Welcome!",
                member_count_text="Member #1",
                template_id=tid,
            ).getvalue()
            b = r.render(
                username="User",
                avatar_url=None,
                guild_name="Guild",
                member_count=1,
                card_type="welcome",
                greeting_title="Welcome!",
                member_count_text="Member #1",
                theme_id=tid,
            ).getvalue()
            assert a == b

    def test_template_id_precedence_over_theme_id(self) -> None:
        from bot.services.greeting_renderer import PillowGreetingRenderer

        r = PillowGreetingRenderer()
        common: _RenderKwargs = {
            "username": "User",
            "avatar_url": None,
            "guild_name": "Guild",
            "member_count": 1,
            "card_type": "welcome",
            "greeting_title": "Welcome!",
            "member_count_text": "Member #1",
            "guild_icon_url": None,
        }
        # template_id should win
        a = r.render(template_id="minimal_light", theme_id="gaming_neon", **common).getvalue()
        b = r.render(template_id="minimal_light", **common).getvalue()
        assert a == b
