"""ImageService — rank card generation via Pillow.

Provides :meth:`generate_rank_card` which creates a styled rank card PNG
for a Discord member showing their avatar, username, level, XP bar, and
server rank.

All Pillow work is synchronous by design; callers MUST wrap it in
:func:`asyncio.to_thread` to avoid blocking the event loop.
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
# Constants — rank card layout
# ---------------------------------------------------------------------------

CARD_WIDTH = 934
CARD_HEIGHT = 282

# Colors (RGBA)
BG_TOP = (43, 45, 49, 255)        # #2b2d31
BG_BOTTOM = (30, 31, 34, 255)     # #1e1f22
USERNAME_COLOR = (255, 255, 255, 255)
LEVEL_COLOR = (114, 137, 218, 255)  # #7289da
XP_BAR_BG = (78, 80, 88, 255)       # #4e5058
XP_BAR_FILL = (114, 137, 218, 255)  # #7289da
XP_TEXT_COLOR = (185, 187, 190, 255)  # #b9bbbe
RANK_COLOR = (255, 255, 255, 255)

# Layout positions
AVATAR_X = 30
AVATAR_Y = 77
AVATAR_SIZE = 128

USERNAME_X = 190
USERNAME_Y = 60
LEVEL_X = 190
LEVEL_Y = 100

PROGRESS_BAR_X = 190
PROGRESS_BAR_Y = 180
PROGRESS_BAR_WIDTH = 600
PROGRESS_BAR_HEIGHT = 20
PROGRESS_BAR_RADIUS = 8

XP_TEXT_X = 190
XP_TEXT_Y = 210

RANK_X = 850  # right edge area
RANK_Y = 60

# Font paths (relative to project root)
_FONT_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
_FONT_REGULAR = str(_FONT_DIR / "Inter-Regular.ttf")

# Avatar timeout / size
AVATAR_FETCH_TIMEOUT = 10  # seconds
MAX_USERNAME_DISPLAY = 32  # chars before truncation


class ImageService:
    """Synchronous rank card generator using Pillow.

    All methods are synchronous.  Call from async code via
    ``await asyncio.to_thread(service.generate_rank_card, ...)``.
    """

    __slots__ = ("_font_regular_path",)

    def __init__(self, font_regular_path: str | None = None) -> None:
        """Initialise the service with an optional custom font path.

        Args:
            font_regular_path: Path to Inter-Regular.ttf.  Defaults to
                ``assets/fonts/Inter-Regular.ttf`` relative to the project root.
        """
        self._font_regular_path = font_regular_path or _FONT_REGULAR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_rank_card(
        self,
        username: str,
        avatar_url: str | None,
        xp: int,
        level: int,
        rank: int,
        xp_for_current: float,
        xp_for_next: float,
    ) -> io.BytesIO:
        """Generate a rank card PNG image.

        Args:
            username: The member's display name.
            avatar_url: URL to the member's avatar, or ``None`` for a
                default placeholder.
            xp: Total XP (for display text).
            level: Current level number.
            rank: Server rank (1-indexed, e.g. 1 = #1).
            xp_for_current: XP earned at the current level (numerator).
            xp_for_next: Total XP needed to advance to the next level
                (denominator).

        Returns:
            A :class:`io.BytesIO` buffer containing the PNG image, ready
            to be sent as a ``discord.File``.
        """
        # -- Base image with gradient background --------------------------
        img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT))
        draw = ImageDraw.Draw(img)

        for y in range(CARD_HEIGHT):
            ratio = y / CARD_HEIGHT
            r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * ratio)
            g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * ratio)
            b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * ratio)
            draw.line([(0, y), (CARD_WIDTH, y)], fill=(r, g, b, 255))

        # -- Load fonts ---------------------------------------------------
        font_username = self._load_font(28)
        font_username_bold = self._load_font(28)  # same file — Inter has no separate bold
        font_level = self._load_font(20)
        font_xp_text = self._load_font(16)
        font_rank = self._load_font(36)

        # -- Avatar (circular crop) ----------------------------------------
        avatar = self._fetch_avatar(avatar_url)
        if avatar is not None:
            avatar = avatar.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
            mask = Image.new("L", (AVATAR_SIZE, AVATAR_SIZE), 0)
            ImageDraw.Draw(mask).ellipse(
                (0, 0, AVATAR_SIZE, AVATAR_SIZE), fill=255
            )
            avatar.putalpha(mask)
            img.paste(avatar, (AVATAR_X, AVATAR_Y), avatar)

        # -- Username (truncate if too long) ------------------------------
        display_name = username[:MAX_USERNAME_DISPLAY]
        if len(username) > MAX_USERNAME_DISPLAY:
            display_name += "…"
        draw.text(
            (USERNAME_X, USERNAME_Y),
            display_name,
            fill=USERNAME_COLOR,
            font=font_username_bold,
        )

        # -- Level label --------------------------------------------------
        draw.text(
            (LEVEL_X, LEVEL_Y),
            f"Level {level}",
            fill=LEVEL_COLOR,
            font=font_level,
        )

        # -- XP progress bar ----------------------------------------------
        # Background
        bar_left = PROGRESS_BAR_X
        bar_right = PROGRESS_BAR_X + PROGRESS_BAR_WIDTH
        bar_top = PROGRESS_BAR_Y
        bar_bottom = PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT
        draw.rounded_rectangle(
            (bar_left, bar_top, bar_right, bar_bottom),
            radius=PROGRESS_BAR_RADIUS,
            fill=XP_BAR_BG,
        )

        # Fill portion
        if xp_for_next > 0:
            fill_ratio = min(xp_for_current / xp_for_next, 1.0)
        else:
            fill_ratio = 1.0  # edge case: max level with no "next"
        fill_width = int(PROGRESS_BAR_WIDTH * fill_ratio)

        if fill_width > 0:
            fill_right = bar_left + fill_width
            # Clamp so we don't draw a bar wider than the bg.
            fill_right = min(fill_right, bar_right)
            draw.rounded_rectangle(
                (bar_left, bar_top, fill_right, bar_bottom),
                radius=PROGRESS_BAR_RADIUS,
                fill=XP_BAR_FILL,
            )

        # -- XP text (e.g. "1250 / 2000 XP") -------------------------------
        xp_text = f"{int(xp_for_current):,} / {int(xp_for_next):,} XP"
        draw.text(
            (XP_TEXT_X, XP_TEXT_Y),
            xp_text,
            fill=XP_TEXT_COLOR,
            font=font_xp_text,
        )

        # -- Rank number (right-aligned) -----------------------------------
        rank_text = f"#{rank}"
        # Measure text to right-align
        rank_bbox = draw.textbbox((0, 0), rank_text, font=font_rank)
        rank_width = rank_bbox[2] - rank_bbox[0]
        draw.text(
            (RANK_X - rank_width, RANK_Y),
            rank_text,
            fill=RANK_COLOR,
            font=font_rank,
        )

        # -- Encode to PNG buffer ------------------------------------------
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    # ------------------------------------------------------------------
    # Greeting card generation
    # ------------------------------------------------------------------

    # Greeting card layout constants
    GREETING_AVATAR_X = 60
    GREETING_AVATAR_Y = 77
    GREETING_AVATAR_SIZE = 128

    GREETING_TITLE_X = 210
    GREETING_TITLE_Y = 80

    GREETING_COUNT_X = 210
    GREETING_COUNT_Y = 170

    GREETING_TITLE_COLOR = (255, 255, 255, 255)
    GREETING_COUNT_COLOR = (185, 187, 190, 255)

    def generate_greeting_card(
        self,
        username: str,
        avatar_url: str | None,
        guild_name: str,
        member_count: int,
        card_type: str = "welcome",
    ) -> io.BytesIO:
        """Generate a welcome or goodbye card PNG image.

        Args:
            username: The member's display name.
            avatar_url: URL to the member's avatar, or ``None`` for a
                default placeholder.
            guild_name: Name of the guild (server).
            member_count: Current member count for the guild.
            card_type: ``"welcome"`` or ``"goodbye"`` — determines the
                greeting text.  Unknown values fall back to ``"welcome"``.

        Returns:
            A :class:`io.BytesIO` buffer containing the PNG image.
        """
        if card_type not in ("welcome", "goodbye"):
            card_type = "welcome"

        # -- Base image with gradient background --------------------------
        img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT))
        draw = ImageDraw.Draw(img)

        for y in range(CARD_HEIGHT):
            ratio = y / CARD_HEIGHT
            r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * ratio)
            g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * ratio)
            b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * ratio)
            draw.line([(0, y), (CARD_WIDTH, y)], fill=(r, g, b, 255))

        # -- Load fonts ---------------------------------------------------
        font_title = self._load_font(32)
        font_count = self._load_font(22)

        # -- Avatar (circular crop) ----------------------------------------
        avatar = self._fetch_avatar(avatar_url)
        if avatar is not None:
            avatar = avatar.resize(
                (self.GREETING_AVATAR_SIZE, self.GREETING_AVATAR_SIZE),
                Image.LANCZOS,
            )
            mask = Image.new("L", (self.GREETING_AVATAR_SIZE, self.GREETING_AVATAR_SIZE), 0)
            ImageDraw.Draw(mask).ellipse(
                (0, 0, self.GREETING_AVATAR_SIZE, self.GREETING_AVATAR_SIZE),
                fill=255,
            )
            avatar.putalpha(mask)
            img.paste(
                avatar,
                (self.GREETING_AVATAR_X, self.GREETING_AVATAR_Y),
                avatar,
            )

        # -- Greeting title (e.g. "Welcome, Username!") --------------------
        greeting = "Welcome" if card_type == "welcome" else "Goodbye"

        # Truncate username if too long.
        display_name = username[:MAX_USERNAME_DISPLAY]
        if len(username) > MAX_USERNAME_DISPLAY:
            display_name += "…"

        title_text = f"{greeting},\n{display_name}!"
        draw.text(
            (self.GREETING_TITLE_X, self.GREETING_TITLE_Y),
            title_text,
            fill=self.GREETING_TITLE_COLOR,
            font=font_title,
        )

        # -- Member count --------------------------------------------------
        count_text = f"Member #{member_count:,}"
        draw.text(
            (self.GREETING_COUNT_X, self.GREETING_COUNT_Y),
            count_text,
            fill=self.GREETING_COUNT_COLOR,
            font=font_count,
        )

        # -- Encode to PNG buffer ------------------------------------------
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_font(self, size: int) -> FreeTypeFont:
        """Load the Inter Regular font at the given *size*."""
        try:
            return ImageFont.truetype(self._font_regular_path, size)
        except OSError:
            logger.warning(
                "Could not load font at %s — falling back to default",
                self._font_regular_path,
            )
            return ImageFont.load_default()

    @staticmethod
    def _fetch_avatar(avatar_url: str | None) -> Image.Image | None:
        """Download and return an avatar as a Pillow Image, or ``None``.

        Returns ``None`` for missing URLs, fetch errors, or non-image
        responses so the rank card renders cleanly without an avatar.
        """
        if not avatar_url:
            return None

        try:
            req = urllib.request.Request(
                avatar_url,
                headers={"User-Agent": "NebulosaBot/1.0 (rank card)"},
            )
            with urllib.request.urlopen(req, timeout=AVATAR_FETCH_TIMEOUT) as resp:  # noqa: S310 — user-supplied URL is expected
                data = resp.read()
            return Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception:
            logger.debug(
                "Failed to fetch avatar from %s — using placeholder",
                avatar_url,
                exc_info=True,
            )
            return None
