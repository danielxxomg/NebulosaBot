"""ImageService — DEPRECATED thin shim delegating to RankRenderer / GreetingRenderer.

DEPRECATED. The canonical implementations now live in
:mod:`bot.services.rank_renderer` and :mod:`bot.services.greeting_renderer`
via :mod:`bot.services.shared_assets` (spec R-1: rank-card generation is owned
by ``RankRenderer``; WG-4: greeting cards by ``GreetingRenderer``). This class
only *delegates* — it owns no rendering logic — and is retained solely so
existing callers (``bot/cogs/stellar.py`` and the legacy/PR2 test suites that
mock ``bot.image_service.generate_rank_card`` / ``generate_greeting_card``)
keep working. ``GREETING_ACCENT`` below is a legacy RGBA back-compat constant
for tests that patch ``ImageService``; the branded accent source of truth is
``bot.utils.brand.GREETING_ACCENT`` (== ``brand.ACCENT``), used by
``PillowGreetingRenderer``. New code MUST import the renderers directly; this
shim will be removed once ``stellar.py`` and the legacy suites migrate.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw  # noqa: F401 -- re-exported for tests that patch bot.services.image_service.ImageDraw

from bot.services import shared_assets
from bot.services.greeting_renderer import PillowGreetingRenderer
from bot.services.rank_renderer import RankRenderer


class ImageService:
    """DEPRECATED thin compatibility shim delegating to the split renderers.

    The methods below do NOT own rendering — they forward to
    :class:`RankRenderer` and :class:`PillowGreetingRenderer` (spec R-1/WG-4
    owners). Kept so legacy callers and mock-based tests keep working. Callers
    MUST wrap Pillow work in :func:`asyncio.to_thread` to avoid blocking the
    event loop.
    """

    # Re-expose greeting layout constants for tests that patch ImageService.
    GREETING_GUILD_ICON_X = 28
    GREETING_GUILD_ICON_Y = 24
    GREETING_GUILD_ICON_SIZE = 48
    GREETING_AVATAR_X = 54
    GREETING_AVATAR_Y = 92
    GREETING_AVATAR_SIZE = 128
    GREETING_TITLE_X = 210
    GREETING_TITLE_Y = 80
    GREETING_COUNT_X = 210
    GREETING_COUNT_Y = 170
    GREETING_GUILD_NAME_X = 210
    GREETING_GUILD_NAME_Y = 28
    # Keep legacy accent for back-compat; greeting path uses brand.ACCENT via PillowGreetingRenderer.
    GREETING_ACCENT = (114, 137, 218, 255)
    GREETING_PANEL = (255, 255, 255, 18)
    GREETING_PLACEHOLDER = (74, 78, 91, 255)
    GREETING_PLACEHOLDER_INNER = (56, 59, 68, 255)
    GREETING_TITLE_COLOR = (255, 255, 255, 255)
    GREETING_COUNT_COLOR = (185, 187, 190, 255)

    __slots__ = ("_greeting_renderer", "_rank_renderer")

    def __init__(self, font_regular_path: str | None = None) -> None:
        self._rank_renderer = RankRenderer(font_path=font_regular_path)
        self._greeting_renderer = PillowGreetingRenderer(font_path=font_regular_path)

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
        """Delegate to :class:`RankRenderer` (shim)."""
        return self._rank_renderer.generate_rank_card(
            username=username,
            avatar_url=avatar_url,
            xp=xp,
            level=level,
            rank=rank,
            xp_for_current=xp_for_current,
            xp_for_next=xp_for_next,
        )

    def generate_greeting_card(
        self,
        username: str,
        avatar_url: str | None,
        guild_name: str,
        member_count: int,
        card_type: str = "welcome",
        greeting_title: str | None = None,
        member_count_text: str | None = None,
        guild_icon_url: str | None = None,
    ) -> io.BytesIO:
        """Delegate to :class:`PillowGreetingRenderer` (shim)."""
        # Preserve the old rendering contract for omitted strings: the legacy
        # ImageService rendered ``"Welcome,\n{display}!"`` with a comma.
        # The new PillowGreetingRenderer expects the locale to supply punctuation,
        # so the shim must emulate the legacy fallback exactly.
        if greeting_title is None:
            # Legacy fallback includes a comma; emulate by calling the renderer
            # with "Welcome," so f"{greeting_title}\n{display}!" → "Welcome,\n{display}!"
            greeting_title = "Welcome," if card_type == "welcome" else "Goodbye,"
        if member_count_text is None:
            member_count_text = f"Member #{member_count:,}"
        # Honor patches to ImageService._fetch_avatar (legacy tests) by forwarding
        # to shared_assets for the duration of this call.
        orig_fetch = shared_assets._fetch_avatar
        orig_safe = shared_assets._safe_fetch_avatar
        # If the class-level _fetch_avatar has been patched (MagicMock), use it.
        cls_fetch = getattr(self.__class__, "_fetch_avatar", None)
        # Detect if _fetch_avatar is mocked (has call tracking)
        from unittest.mock import MagicMock

        use_cls_fetch = isinstance(cls_fetch, MagicMock) and cls_fetch is not orig_fetch  # type: ignore[arg-type]
        if use_cls_fetch:
            shared_assets._fetch_avatar = cls_fetch  # type: ignore[assignment]

            def _patched_safe(url: str | None):  # type: ignore[no-untyped-def]
                try:
                    return cls_fetch(url)  # type: ignore[operator]
                except Exception:
                    import logging

                    logging.getLogger(__name__).debug(
                        "Greeting card asset fetch failed — using placeholder", exc_info=True
                    )
                    return None

            shared_assets._safe_fetch_avatar = _patched_safe  # type: ignore[assignment]
        try:
            return self._greeting_renderer.render(
                username=username,
                avatar_url=avatar_url,
                guild_name=guild_name,
                member_count=member_count,
                card_type=card_type,
                greeting_title=greeting_title,
                member_count_text=member_count_text,
                guild_icon_url=guild_icon_url,
            )
        finally:
            if use_cls_fetch:
                shared_assets._fetch_avatar = orig_fetch
                shared_assets._safe_fetch_avatar = orig_safe

    # Back-compat for tests that patch ImageService._fetch_avatar
    @staticmethod
    def _fetch_avatar(avatar_url: str | None):  # type: ignore[no-untyped-def]
        return shared_assets._fetch_avatar(avatar_url)

    @staticmethod
    def _safe_fetch_avatar(avatar_url: str | None):  # type: ignore[no-untyped-def]
        return shared_assets._safe_fetch_avatar(avatar_url)
