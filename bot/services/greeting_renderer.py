"""Greeting card renderer — Protocol + Pillow default.

Accent is read from :mod:`bot.utils.brand.ACCENT` (single source of truth);
no hex literals appear outside ``brand.py``. Font ``OSError`` falls back to
``ImageFont.load_default()`` with a WARNING.

Services layer — MUST NOT import cogs or views.
"""

from __future__ import annotations

import io
import logging
from typing import Protocol, runtime_checkable

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
_GREETING_PANEL = (255, 255, 255, 18)


_GREETING_TITLE_COLOR = (255, 255, 255, 255)
_GREETING_COUNT_COLOR = (185, 187, 190, 255)


def _brand_accent_rgba() -> tuple[int, int, int, int]:
    """Return brand accent as RGBA tuple derived from ``brand.ACCENT``."""
    v = brand.ACCENT
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255, 255)


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
