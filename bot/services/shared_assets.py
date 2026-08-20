"""Shared rendering assets for greeting and rank renderers.

Centralizes the gradient loop, font loader, and avatar helpers so neither
renderer duplicates code. Services layer — MUST NOT import cogs or views.
"""

from __future__ import annotations

import io
import logging
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from PIL.ImageFont import FreeTypeFont

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

CARD_WIDTH = 934
CARD_HEIGHT = 282

BG_TOP = (43, 45, 49, 255)  # #2b2d31
BG_BOTTOM = (30, 31, 34, 255)  # #1e1f22

_FONT_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
_FONT_REGULAR = str(_FONT_DIR / "Inter-Regular.ttf")

AVATAR_FETCH_TIMEOUT = 10  # seconds
MAX_USERNAME_DISPLAY = 32  # chars before truncation

# Greeting placeholder palette (rank uses transparent fallback)
GREETING_PLACEHOLDER = (74, 78, 91, 255)
GREETING_PLACEHOLDER_INNER = (56, 59, 68, 255)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _card_base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Create base RGBA image with vertical gradient background.

    Returns:
        Tuple of (image, draw) with gradient already drawn.
    """
    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(CARD_HEIGHT):
        ratio = y / CARD_HEIGHT
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * ratio)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * ratio)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * ratio)
        draw.line([(0, y), (CARD_WIDTH, y)], fill=(r, g, b, 255))
    return img, draw


def _load_font(size: int, font_path: str | None = None) -> FreeTypeFont:
    """Load the Inter Regular font at the given *size*.

    Falls back to :func:`ImageFont.load_default` on ``OSError`` and logs a
    WARNING so the card still renders.

    Args:
        size: Font point size.
        font_path: Optional custom font path. Defaults to
            ``assets/fonts/Inter-Regular.ttf``.
    """
    path = font_path or _FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        logger.warning(
            "Could not load font at %s — falling back to default",
            path,
        )
        return ImageFont.load_default()  # type: ignore[return-value]  # stub mismatch; runtime is correct


def _fetch_avatar(avatar_url: str | None) -> Image.Image | None:
    """Download and return an avatar as a Pillow Image, or ``None``.

    Returns ``None`` for missing URLs, fetch errors, or non-image
    responses so the card renders without an avatar.
    """
    if not avatar_url:
        return None

    try:
        req = urllib.request.Request(  # noqa: S310 -- Discord CDN https; scheme validated by caller
            avatar_url,
            headers={"User-Agent": "NebulosaBot/1.0 (rank card)"},
        )
        with urllib.request.urlopen(req, timeout=AVATAR_FETCH_TIMEOUT) as resp:  # noqa: S310 -- caller-supplied Discord CDN URL
            data = resp.read()
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        logger.debug(
            "Failed to fetch avatar from %s — using placeholder",
            avatar_url,
            exc_info=True,
        )
        return None


def _safe_fetch_avatar(avatar_url: str | None) -> Image.Image | None:
    """Fetch an optional image without allowing asset failure to abort rendering."""
    try:
        return _fetch_avatar(avatar_url)
    except Exception:
        logger.debug("Greeting card asset fetch failed — using placeholder", exc_info=True)
        return None


def _paste_circular_asset(
    img: Image.Image,
    asset: Image.Image | None,
    x: int,
    y: int,
    size: int,
    placeholder_color: tuple[int, int, int, int],
) -> None:
    """Paste a circular asset or deterministic placeholder into *img*.

    Args:
        img: The base image to paste into.
        asset: The asset image, or ``None`` for placeholder.
        x: Left coordinate.
        y: Top coordinate.
        size: Diameter of the circular area.
        placeholder_color: Fill color when *asset* is ``None``.
    """
    draw = ImageDraw.Draw(img)
    bounds = (x, y, x + size, y + size)
    if asset is None:
        draw.ellipse(bounds, fill=placeholder_color)
        inset = max(4, size // 8)
        draw.ellipse(
            (x + inset, y + inset, x + size - inset, y + size - inset),
            fill=GREETING_PLACEHOLDER_INNER,
        )
        return

    resized = asset.convert("RGBA").resize(
        (size, size),
        Image.LANCZOS,  # type: ignore[attr-defined]  # Pillow exposes LANCZOS at runtime but stubs omit it
    )
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    resized.putalpha(mask)
    img.paste(resized, (x, y), resized)
