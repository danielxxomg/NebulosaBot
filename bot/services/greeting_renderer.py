"""Greeting card renderer — Protocol + Pillow default.

Accent is read from :mod:`bot.utils.brand.ACCENT` (single source of truth);
no hex literals appear outside ``brand.py``. Font ``OSError`` falls back to
``ImageFont.load_default()`` with a WARNING.

Services layer — MUST NOT import cogs or views.
"""

from __future__ import annotations

import io
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from PIL import Image, ImageDraw, ImageFilter

from bot.services import shared_assets
from bot.utils import brand

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Greeting card layout constants (services layer)
# ---------------------------------------------------------------------------

_GREETING_GUILD_ICON_X = 28
_GREETING_GUILD_ICON_Y = 24
_GREETING_GUILD_ICON_SIZE = 48

_GREETING_AVATAR_X = 54
_GREETING_AVATAR_Y = 92
_GREETING_AVATAR_SIZE = 128

_GREETING_TITLE_X = 210
_GREETING_TITLE_Y = 80

_GREETING_COUNT_X = 210
_GREETING_COUNT_Y = 170

_GREETING_GUILD_NAME_X = 210
_GREETING_GUILD_NAME_Y = 28
_GREETING_PANEL = brand.PANEL_OVERLAY


_GREETING_TITLE_COLOR = (255, 255, 255, 255)
_GREETING_COUNT_COLOR = brand.MUTED_TEXT  # dedupe: == rank XP text color (S4.7)


def _brand_accent_rgba() -> tuple[int, int, int, int]:
    """Return brand accent as RGBA tuple derived from ``brand.ACCENT``."""
    v = brand.ACCENT
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255, 255)


def _brand_neon_rgba_a() -> tuple[int, int, int, int]:
    v = brand.ACCENT_A
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255, 255)


def _brand_neon_rgba_b() -> tuple[int, int, int, int]:
    v = brand.ACCENT_B
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255, 255)


def _hexagon_points(cx: int, cy: int, radius: int) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(6):
        ang = math.radians(60 * i - 30)
        pts.append((cx + radius * math.cos(ang), cy + radius * math.sin(ang)))
    return pts


def _render_neon_overlay(img: Image.Image) -> None:
    """Draw neon hex polygon + GaussianBlur glow diagonal ACCENT_A→ACCENT_B."""
    w, h = img.size
    # Glow layer: hex polygon with blur
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    cx, cy = w - 110, h // 2
    pts = _hexagon_points(cx, cy, 62)
    neon_a = _brand_neon_rgba_a()
    neon_b = _brand_neon_rgba_b()
    # Diagonal accent: two-tone hex — outer glow in ACCENT_A, inner in ACCENT_B
    glow_draw.polygon(pts, fill=neon_a, outline=neon_a)
    # Inner hex slightly smaller in ACCENT_B
    inner = _hexagon_points(cx, cy, 44)
    glow_draw.polygon(inner, fill=neon_b, outline=neon_b)
    # Blur glow
    blurred = glow.filter(ImageFilter.GaussianBlur(radius=8))
    img.alpha_composite(blurred)
    # Sharp hex on top
    draw = ImageDraw.Draw(img)
    draw.polygon(pts, outline=neon_a, width=2)
    draw.polygon(inner, outline=neon_b, width=1)
    # Diagonal accent line ACCENT_A→ACCENT_B
    draw.line([(18, 16), (w - 18, h - 16)], fill=neon_a, width=2)
    draw.line([(w - 18, 16), (18, h - 16)], fill=neon_b, width=1)


def _render_sunset_wave_overlay(img: Image.Image) -> None:
    """Sunset diagonal using WARNING+ERROR low-alpha + PANEL_OVERLAY."""
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    # Diagonal wash: WARNING with low alpha
    warning = brand.WARNING
    error = brand.ERROR
    # Use low-alpha variants
    w_rgba = ((warning >> 16) & 255, (warning >> 8) & 255, warning & 255, 38)
    e_rgba = ((error >> 16) & 255, (error >> 8) & 255, error & 255, 32)
    # Diagonal polygons
    od.polygon([(0, 0), (w, 0), (w, h // 2), (0, h)], fill=w_rgba)
    od.polygon([(w // 2, 0), (w, 0), (w, h), (0, h)], fill=e_rgba)
    # Panel overlay wash
    od.rectangle((18, 16, w - 18, 56), fill=brand.PANEL_OVERLAY)
    img.alpha_composite(overlay)


def _render_minimal_light_overlay(img: Image.Image) -> None:
    """Minimal: single ACCENT hairline + CARD_BG/MUTED_TEXT subtle accent."""
    w, h = img.size
    draw = ImageDraw.Draw(img)
    accent = _brand_accent_rgba()
    # Hairline top accent
    draw.line([(18, 18), (w - 18, 18)], fill=accent, width=1)
    # Subtle bottom line using MUTED_TEXT low alpha
    mt = brand.MUTED_TEXT
    mt_low = (mt[0], mt[1], mt[2], 40)
    draw.line([(18, h - 18), (w - 18, h - 18)], fill=mt_low, width=1)


@dataclass(frozen=True)
class Template:
    id: str
    label_key: str
    description_key: str
    overlay_fn: Callable[[Image.Image], None] | None


TEMPLATE_REGISTRY: dict[str, Template] = {
    "default": Template(
        id="default",
        label_key="templates.greeting.default.label",
        description_key="templates.greeting.default.description",
        overlay_fn=None,
    ),
    "gaming_neon": Template(
        id="gaming_neon",
        label_key="templates.greeting.gaming_neon.label",
        description_key="templates.greeting.gaming_neon.description",
        overlay_fn=_render_neon_overlay,
    ),
    "sunset_wave": Template(
        id="sunset_wave",
        label_key="templates.greeting.sunset_wave.label",
        description_key="templates.greeting.sunset_wave.description",
        overlay_fn=_render_sunset_wave_overlay,
    ),
    "minimal_light": Template(
        id="minimal_light",
        label_key="templates.greeting.minimal_light.label",
        description_key="templates.greeting.minimal_light.description",
        overlay_fn=_render_minimal_light_overlay,
    ),
}


@runtime_checkable
class GreetingRenderer(Protocol):
    """Render a branded greeting card PNG from pre-translated strings.

    Implementations MUST NOT resolve translations (no ``t()`` calls).
    Identity inputs (avatar, guild icon) are fetched off the event loop;
    callers wrap :meth:`render` in :func:`asyncio.to_thread`.
    """

    def render(
        self,
        *,
        username: str,
        avatar_url: str | None,
        guild_name: str,
        member_count: int,
        card_type: str,  # "welcome" | "goodbye"
        greeting_title: str,  # pre-translated
        member_count_text: str,  # pre-translated
        guild_icon_url: str | None,
        theme_id: str | None = None,
        template_id: str | None = None,
    ) -> io.BytesIO: ...


class PillowGreetingRenderer:
    """Cycle 1 default renderer. Accent from ``brand.ACCENT`` (no hex)."""

    __slots__ = ("_font_path",)

    def __init__(self, font_path: str | None = None) -> None:
        self._font_path = font_path

    def render(
        self,
        *,
        username: str,
        avatar_url: str | None,
        guild_name: str,
        member_count: int,
        card_type: str = "welcome",
        greeting_title: str,
        member_count_text: str,
        guild_icon_url: str | None = None,
        theme_id: str | None = None,
        template_id: str | None = None,
    ) -> io.BytesIO:
        """Render a welcome or goodbye card PNG image.

        Args:
            username: The member's display name.
            avatar_url: URL to the member's avatar, or ``None``.
            guild_name: Name of the guild.
            member_count: Current member count.
            card_type: ``"welcome"`` or ``"goodbye"``.
            greeting_title: Pre-translated greeting title.
            member_count_text: Pre-translated member-count text.
            guild_icon_url: URL to the guild icon, or ``None``.

        Returns:
            A :class:`io.BytesIO` buffer containing the PNG image.
        """
        if card_type not in ("welcome", "goodbye"):
            card_type = "welcome"

        accent = _brand_accent_rgba()

        # -- Base image with gradient background --------------------------
        img, draw = shared_assets._card_base()

        # -- Template overlay (dual-param: template_id or theme_id or "default") --
        resolved = template_id or theme_id or "default"
        tmpl = TEMPLATE_REGISTRY.get(resolved)
        if tmpl is None:
            tmpl = TEMPLATE_REGISTRY["default"]
        if tmpl.overlay_fn is not None:
            tmpl.overlay_fn(img)
            # Re-acquire draw after overlay (alpha_composite invalidates prior draw)
            draw = ImageDraw.Draw(img)

        # -- Branded hierarchy ---------------------------------------------
        draw.rounded_rectangle(
            (18, 16, shared_assets.CARD_WIDTH - 18, shared_assets.CARD_HEIGHT - 16),
            radius=18,
            outline=(255, 255, 255, 34),
            width=2,
        )
        draw.rounded_rectangle(
            (18, 16, shared_assets.CARD_WIDTH - 18, 56),
            radius=18,
            fill=_GREETING_PANEL,
        )
        draw.rectangle((18, 48, shared_assets.CARD_WIDTH - 18, 56), fill=_GREETING_PANEL)
        draw.rectangle((18, 16, 24, shared_assets.CARD_HEIGHT - 16), fill=accent)

        # -- Load fonts ---------------------------------------------------
        font_guild = shared_assets._load_font(16, font_path=self._font_path)
        font_title = shared_assets._load_font(32, font_path=self._font_path)
        font_count = shared_assets._load_font(22, font_path=self._font_path)

        # -- Guild identity and member avatar -----------------------------
        guild_icon = shared_assets._safe_fetch_avatar(guild_icon_url)
        shared_assets._paste_circular_asset(
            img,
            guild_icon,
            _GREETING_GUILD_ICON_X,
            _GREETING_GUILD_ICON_Y,
            _GREETING_GUILD_ICON_SIZE,
            accent,
        )

        avatar = shared_assets._safe_fetch_avatar(avatar_url)
        shared_assets._paste_circular_asset(
            img,
            avatar,
            _GREETING_AVATAR_X,
            _GREETING_AVATAR_Y,
            _GREETING_AVATAR_SIZE,
            shared_assets.GREETING_PLACEHOLDER,
        )

        guild_display_name = guild_name.strip()[:42] or "Nebulosa"
        draw.text(
            (_GREETING_GUILD_NAME_X, _GREETING_GUILD_NAME_Y),
            guild_display_name,
            fill=accent,
            font=font_guild,
        )

        # -- Greeting title ------------------------------------------------
        display_name = username[: shared_assets.MAX_USERNAME_DISPLAY]
        if len(username) > shared_assets.MAX_USERNAME_DISPLAY:
            display_name += "…"

        # greeting_title is pre-translated; combine with display name.
        if not greeting_title:
            # Fallback if caller passes empty string.
            greeting_title = "Welcome" if card_type == "welcome" else "Goodbye"
        title_text = f"{greeting_title}\n{display_name}!"
        draw.text(
            (_GREETING_TITLE_X, _GREETING_TITLE_Y),
            title_text,
            fill=_GREETING_TITLE_COLOR,
            font=font_title,
        )

        # -- Member count --------------------------------------------------
        count_text = member_count_text or f"Member #{member_count:,}"
        draw.text(
            (_GREETING_COUNT_X, _GREETING_COUNT_Y),
            count_text,
            fill=_GREETING_COUNT_COLOR,
            font=font_count,
        )

        # -- Encode to PNG buffer ------------------------------------------
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
