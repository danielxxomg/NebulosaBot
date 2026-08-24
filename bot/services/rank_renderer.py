"""Rank card renderer — SRP split from ImageService.

Shares gradient loop, font loader, and avatar helpers via
``bot.services.shared_assets`` so no code is duplicated. The circular avatar
paste and missing-avatar placeholder are delegated to the shared
``_paste_circular_asset`` / ``_safe_fetch_avatar`` helpers (spec R-3: avatar
helpers are shared; missing avatar uses a placeholder).
Services layer — MUST NOT import cogs or views.
"""

from __future__ import annotations

import io

from bot.services import shared_assets
from bot.utils.brand import LEGACY_BLURPLE_RGBA, MUTED_TEXT

# ---------------------------------------------------------------------------
# Rank card layout constants (mirrors image_service for byte-identity)
# ---------------------------------------------------------------------------

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

RANK_X = 850
RANK_Y = 60

# Colors (RGBA) — single-sourced via brand tokens (S4.7); values identical
# to the pre-consolidation literals so golden bytes are unchanged.
# brand.ACCENT is greeting-side.
USERNAME_COLOR = (255, 255, 255, 255)
LEVEL_COLOR = LEGACY_BLURPLE_RGBA  # rank keeps legacy blurple for golden-byte identity
XP_BAR_BG = (78, 80, 88, 255)
XP_BAR_FILL = LEGACY_BLURPLE_RGBA
# Dedupe (S4.7): XP text color == greeting count color == brand.MUTED_TEXT.
XP_TEXT_COLOR = MUTED_TEXT
RANK_COLOR = (255, 255, 255, 255)

# Rank-side placeholder for a missing avatar (spec R-3). Uses the shared
# greeting placeholder palette so the fallback visual is consistent across
# renderers; the shared _paste_circular_asset draws the ellipse.
RANK_AVATAR_PLACEHOLDER = shared_assets.GREETING_PLACEHOLDER


class RankRenderer:
    """Synchronous rank card generator using Pillow via shared assets.

    All methods are synchronous. Call from async code via
    ``await asyncio.to_thread(renderer.generate_rank_card, ...)``.
    """

    __slots__ = ("_font_path",)

    def __init__(self, font_path: str | None = None) -> None:
        """Initialise the renderer with an optional custom font path."""
        self._font_path = font_path

    def generate_rank_card(
        self,
        username: str,
        avatar_url: str | None,
        xp: int,  # noqa: ARG002 -- public API
        level: int,
        rank: int,
        xp_for_current: float,
        xp_for_next: float,
    ) -> io.BytesIO:
        """Generate a rank card PNG image (byte-identical to ImageService)."""
        # -- Base image with gradient background --------------------------
        img, draw = shared_assets._card_base()

        # -- Load fonts ---------------------------------------------------
        font_username_bold = shared_assets._load_font(28, font_path=self._font_path)
        font_level = shared_assets._load_font(20, font_path=self._font_path)
        font_xp_text = shared_assets._load_font(16, font_path=self._font_path)
        font_rank = shared_assets._load_font(36, font_path=self._font_path)

        # -- Avatar (circular crop via shared helper) ---------------------
        # Spec R-3: use shared _safe_fetch_avatar / _paste_circular_asset and
        # render a placeholder when the avatar is missing so the card still
        # shows identity treatment instead of a blank circle.
        avatar = shared_assets._safe_fetch_avatar(avatar_url)
        shared_assets._paste_circular_asset(
            img,
            avatar,
            AVATAR_X,
            AVATAR_Y,
            AVATAR_SIZE,
            RANK_AVATAR_PLACEHOLDER,
        )

        # -- Username (truncate if too long) ------------------------------
        display_name = username[: shared_assets.MAX_USERNAME_DISPLAY]
        if len(username) > shared_assets.MAX_USERNAME_DISPLAY:
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
        bar_left = PROGRESS_BAR_X
        bar_right = PROGRESS_BAR_X + PROGRESS_BAR_WIDTH
        bar_top = PROGRESS_BAR_Y
        bar_bottom = PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT
        draw.rounded_rectangle(
            (bar_left, bar_top, bar_right, bar_bottom),
            radius=PROGRESS_BAR_RADIUS,
            fill=XP_BAR_BG,
        )

        fill_ratio = min(xp_for_current / xp_for_next, 1.0) if xp_for_next > 0 else 1.0
        fill_width = int(PROGRESS_BAR_WIDTH * fill_ratio)

        if fill_width > 0:
            fill_right = min(bar_left + fill_width, bar_right)
            draw.rounded_rectangle(
                (bar_left, bar_top, fill_right, bar_bottom),
                radius=PROGRESS_BAR_RADIUS,
                fill=XP_BAR_FILL,
            )

        # -- XP text -------------------------------------------------------
        xp_text = f"{int(xp_for_current):,} / {int(xp_for_next):,} XP"
        draw.text(
            (XP_TEXT_X, XP_TEXT_Y),
            xp_text,
            fill=XP_TEXT_COLOR,
            font=font_xp_text,
        )

        # -- Rank number (right-aligned) -----------------------------------
        rank_text = f"#{rank}"
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
